"""Achats et receptions : commandes fournisseurs, entree en stock."""
import json

from flask import Blueprint, abort, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required

from app.extensions import db
from app.models.catalog import Product
from app.models.partners import Supplier
from app.models.purchases import (
    PURCHASE_STATUS_BADGES,
    PURCHASE_STATUS_LABELS,
    Purchase,
    PurchaseStatus,
)
from app.security.audit import log_action
from app.security.decorators import admin_password_required, permission_required
from app.security.permissions import P
from app.services import cash as cash_service
from app.services import purchases as purchase_service
from app.services.pagination import paginate
from app.services.stock import dec

purchases_bp = Blueprint("purchases", __name__, url_prefix="/achats")


def _suppliers():
    return Supplier.query.filter_by(active=True).order_by(Supplier.name).all()


def _products():
    return Product.query.filter_by(active=True).order_by(Product.name).all()


@purchases_bp.route("/")
@login_required
@permission_required(P.PURCHASE_VIEW)
def index():
    status = request.args.get("status")
    query = Purchase.query
    if status:
        query = query.filter_by(status=status)
    pager = paginate(query.order_by(Purchase.order_date.desc()))
    return render_template(
        "purchases/index.html",
        pager=pager,
        purchases=pager.items,
        labels=PURCHASE_STATUS_LABELS,
        badges=PURCHASE_STATUS_BADGES,
        status=status,
    )


@purchases_bp.route("/<int:purchase_id>/supprimer", methods=["POST"])
@login_required
@permission_required(P.PURCHASE_PREPARE)
@admin_password_required()
def delete(purchase_id):
    purchase = db.session.get(Purchase, purchase_id) or abort(404)
    if purchase.status not in (PurchaseStatus.BROUILLON, PurchaseStatus.COMMANDE):
        flash("Seul un achat brouillon ou commandé peut être supprimé. Un achat reçu ou annulé se corrige par annulation.", "danger")
        return redirect(url_for("purchases.index"))
    reference = purchase.reference
    db.session.delete(purchase)
    log_action("purchase_delete", entity="purchase", after={"reference": reference}, commit=True)
    flash(f"Achat {reference} supprimé.", "success")
    return redirect(url_for("purchases.index"))


@purchases_bp.route("/nouveau", methods=["GET", "POST"])
@login_required
@permission_required(P.PURCHASE_PREPARE)
def new():
    if request.method == "POST":
        supplier = db.session.get(Supplier, request.form.get("supplier_id", type=int))
        if supplier is None:
            flash("Fournisseur introuvable.", "danger")
            return redirect(url_for("purchases.new"))

        currency = request.form.get("currency") or "CDF"
        try:
            items = json.loads(request.form.get("items_json") or "[]")
        except json.JSONDecodeError:
            items = []

        prepared = []
        for item in items:
            product = db.session.get(Product, item.get("product_id"))
            if product is None:
                continue
            prepared.append(
                {
                    "product": product,
                    "unit_id": item.get("unit_id"),
                    "quantity": item.get("quantity"),
                    "prix_unitaire": item.get("prix_unitaire"),
                }
            )
        if not prepared:
            flash("Ajoutez au moins un produit a l'achat.", "danger")
            return redirect(url_for("purchases.new"))

        expected = request.form.get("expected_date")
        purchase = purchase_service.create_purchase(
            supplier=supplier,
            currency=currency,
            items=prepared,
            user_id=current_user.id,
            expected_date=expected.split("T")[0] if expected else None,
            paid_now=bool(request.form.get("paid_now")),
            notes=(request.form.get("notes") or "").strip() or None,
        )
        log_action(
            "purchase_create",
            entity="purchase",
            entity_uuid=purchase.uuid,
            after={"reference": purchase.reference, "total": str(purchase.montant_total)},
            commit=True,
        )
        flash(f"Achat {purchase.reference} cree (brouillon).", "success")
        return redirect(url_for("purchases.detail", purchase_id=purchase.id))

    return render_template(
        "purchases/form.html",
        suppliers=_suppliers(),
        products=_products(),
    )


@purchases_bp.route("/<int:purchase_id>")
@login_required
@permission_required(P.PURCHASE_VIEW)
def detail(purchase_id):
    purchase = db.session.get(Purchase, purchase_id) or abort(404)
    return render_template(
        "purchases/detail.html",
        purchase=purchase,
        labels=PURCHASE_STATUS_LABELS,
        badges=PURCHASE_STATUS_BADGES,
    )


@purchases_bp.route("/<int:purchase_id>/commander", methods=["POST"])
@login_required
@permission_required(P.PURCHASE_PREPARE)
def order(purchase_id):
    purchase = db.session.get(Purchase, purchase_id) or abort(404)
    if purchase.status != PurchaseStatus.BROUILLON:
        flash("Seul un brouillon peut etre commande.", "warning")
        return redirect(url_for("purchases.detail", purchase_id=purchase.id))
    try:
        purchase_service.mark_ordered(purchase)
    except ValueError as exc:
        flash(str(exc), "danger")
        return redirect(url_for("purchases.detail", purchase_id=purchase.id))
    log_action("purchase_order", entity="purchase", entity_uuid=purchase.uuid, commit=True)
    flash("Achat commande.", "success")
    return redirect(url_for("purchases.detail", purchase_id=purchase.id))


@purchases_bp.route("/<int:purchase_id>/recevoir", methods=["POST"])
@login_required
@permission_required(P.PURCHASE_VALIDATE)
def receive(purchase_id):
    purchase = db.session.get(Purchase, purchase_id) or abort(404)
    if purchase.status == PurchaseStatus.RECEPTIONNEE:
        flash("Cet achat est deja receptionne.", "warning")
        return redirect(url_for("purchases.detail", purchase_id=purchase.id))

    session = cash_service.find_open_session(vendeur_id=current_user.id)
    try:
        purchase_service.receive_purchase(purchase, current_user.id, cash_session=session)
    except ValueError as exc:
        flash(str(exc), "danger")
        return redirect(url_for("purchases.detail", purchase_id=purchase.id))

    log_action(
        "purchase_receive",
        entity="purchase",
        entity_uuid=purchase.uuid,
        after={"total": str(purchase.montant_total), "paid_now": purchase.paid_now},
        commit=True,
    )
    flash(f"Achat {purchase.reference} receptionne : stock mis a jour.", "success")
    return redirect(url_for("purchases.detail", purchase_id=purchase.id))


@purchases_bp.route("/<int:purchase_id>/annuler", methods=["POST"])
@login_required
@permission_required(P.PURCHASE_VALIDATE)
def cancel(purchase_id):
    purchase = db.session.get(Purchase, purchase_id) or abort(404)
    reason = (request.form.get("reason") or "").strip()
    if not reason:
        flash("Le motif d'annulation est obligatoire.", "danger")
        return redirect(url_for("purchases.detail", purchase_id=purchase.id))
    try:
        purchase_service.cancel_purchase(purchase, current_user.id, reason)
    except ValueError as exc:
        flash(str(exc), "danger")
        return redirect(url_for("purchases.detail", purchase_id=purchase.id))
    log_action("purchase_cancel", entity="purchase", entity_uuid=purchase.uuid, reason=reason, commit=True)
    flash("Achat annule (contre-ecriture tracee).", "success")
    return redirect(url_for("purchases.detail", purchase_id=purchase.id))
