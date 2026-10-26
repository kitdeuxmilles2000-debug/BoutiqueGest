"""Point de vente (POS) : panier rapide et encaissement."""
import json
from datetime import date, timedelta

from flask import Blueprint, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required

from app.extensions import db
from app.models.catalog import Product
from app.models.finance import CreditType
from app.models.partners import Customer
from app.models.sales import PAYMENT_LABELS_POS, PaymentMethod
from app.security.audit import log_action
from app.security.decorators import permission_required
from app.security.permissions import P
from app.services import cash as cash_service
from app.services import finance as finance_service
from app.services import pricing as pricing_service
from app.services import sales as sales_service
from app.services.stock import dec

pos_bp = Blueprint("pos", __name__, url_prefix="/pos")


@pos_bp.route("/")
@login_required
@permission_required(P.SALES_CREATE)
def index():
    session = cash_service.find_open_session(vendeur_id=current_user.id)
    if session is None:
        flash("Ouvrez d'abord une caisse pour vendre.", "warning")
        return redirect(url_for("cash.index"))

    currency = session.currency
    catalog = []
    sans_stock = []
    for product in Product.query.filter_by(active=True).order_by(Product.name).all():
        units = sales_service.sellable_units(product, currency)
        if not units:
            continue
        # Seul un stock **valide** rend un produit vendable.
        if dec(product.stock_qty) <= 0:
            sans_stock.append(product)
            continue
        catalog.append({
            "product": product,
            "units": units,
            "stock_text": pricing_service.stock_in_sale_units(product),
            "target": pricing_service.target_margin(product),
        })

    return render_template(
        "pos/index.html",
        session=session,
        catalog=catalog,
        sans_stock=sans_stock,
        currency=currency,
        methods=PaymentMethod,
        payment_labels=PAYMENT_LABELS_POS,
        can_discount=current_user.has_permission(P.SALES_DISCOUNT),
        can_credit=current_user.has_permission(P.CREDITS_MANAGE),
        customers=Customer.query.filter_by(active=True).order_by(Customer.name).all(),
        default_due_date=(date.today() + timedelta(days=30)).isoformat(),
    )


@pos_bp.route("/valider", methods=["POST"])
@login_required
@permission_required(P.SALES_CREATE)
def validate():
    session = cash_service.find_open_session(vendeur_id=current_user.id)
    if session is None:
        flash("Aucune caisse ouverte pour encaisser.", "danger")
        return redirect(url_for("pos.index"))

    try:
        payload = json.loads(request.form.get("payload") or "{}")
    except ValueError:
        payload = {}

    items = []
    for raw in payload.get("items") or []:
        product = db.session.get(Product, raw.get("product_id"))
        quantity = dec(raw.get("quantity"))
        if product is None or quantity <= 0:
            continue
        items.append(
            {"product": product, "unit_id": raw.get("unit_id"), "quantity": quantity}
        )

    if not items:
        flash("Le panier est vide.", "danger")
        return redirect(url_for("pos.index"))

    remise = dec(payload.get("remise")) if current_user.has_permission(P.SALES_DISCOUNT) else dec(0)
    payments = payload.get("payments") or []
    notes = (payload.get("notes") or "").strip() or None

    try:
        # La vente et le credit eventuel sont ecrits dans **la meme transaction** :
        # soit tout passe, soit rien n'est enregistre (pas de vente orpheline).
        sale = sales_service.create_sale(
            current_user.id,
            session,
            session.currency,
            items,
            remise=remise,
            payments=payments,
            notes=notes,
            commit=False,
        )
    except sales_service.StockInsuffisant as exc:
        db.session.rollback()
        flash(str(exc), "danger")
        return redirect(url_for("pos.index"))
    except ValueError as exc:
        db.session.rollback()
        flash(str(exc), "danger")
        return redirect(url_for("pos.index"))

    remaining = dec(sale.montant_total) - dec(sale.montant_paye)
    credit = None
    if remaining > 0:
        customer_id = payload.get("credit_customer_id")
        if not current_user.has_permission(P.CREDITS_MANAGE):
            db.session.rollback()
            flash(
                f"Il reste {remaining} {sale.currency} a payer et vous n'avez pas "
                "le droit de creer un credit. Encaissez la totalite.",
                "danger",
            )
            return redirect(url_for("pos.index"))
        if not customer_id:
            db.session.rollback()
            flash(
                f"Il reste {remaining} {sale.currency} a payer : encaissez la totalite "
                "ou choisissez un client pour mettre le reste a credit.",
                "danger",
            )
            return redirect(url_for("pos.index"))

        customer = db.session.get(Customer, customer_id)
        if customer is None:
            db.session.rollback()
            flash("Client introuvable : la vente n'a pas ete enregistree.", "danger")
            return redirect(url_for("pos.index"))

        plafond = dec(customer.credit_limit)
        if plafond > 0 and (dec(customer.outstanding) + remaining) > plafond:
            db.session.rollback()
            flash(
                f"Plafond de credit depasse pour {customer.name} "
                f"(encours {customer.outstanding} + {remaining} > {plafond}). "
                "Vente annulee : encaissez la totalite ou reglez une partie de l'encours.",
                "danger",
            )
            return redirect(url_for("pos.index"))

        try:
            due_date = finance_service.coerce_date(payload.get("credit_due_date"))
        except ValueError as exc:
            db.session.rollback()
            flash(str(exc), "danger")
            return redirect(url_for("pos.index"))
        if due_date is None:
            due_date = date.today() + timedelta(days=30)

        credit = finance_service.create_credit(
            credit_type=CreditType.CLIENT,
            amount=remaining,
            currency=sale.currency,
            customer=customer,
            sale=sale,
            user_id=current_user.id,
            due_date=due_date,
            commit=False,
        )

    try:
        db.session.commit()
    except Exception:
        db.session.rollback()
        flash("La vente n'a pas pu etre enregistree. Reessayez.", "danger")
        return redirect(url_for("pos.index"))

    log_action(
        "sale_create",
        entity="sale",
        entity_uuid=sale.uuid,
        after={"numero": sale.numero, "total": str(sale.montant_total), "lines": len(items)},
        commit=credit is None,
    )
    if credit is not None:
        log_action(
            "credit_create",
            entity="credit",
            entity_uuid=credit.uuid,
            after={
                "type": "client",
                "amount": str(remaining),
                "sale": sale.numero,
                "echeance": credit.due_date.isoformat() if credit.due_date else None,
            },
            commit=True,
        )
        flash(
            f"Reste de {remaining} {sale.currency} porte au credit de {customer.name} "
            f"(echeance {credit.due_date:%d/%m/%Y}).",
            "info",
        )

    flash(f"Vente {sale.numero} enregistree.", "success")
    return redirect(url_for("sales.detail", sale_id=sale.id))
