"""Ventes : liste, detail (recu), annulation et remboursement."""
from datetime import datetime

from flask import Blueprint, abort, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required

from app.extensions import db
from app.models.sales import (
    PAYMENT_LABELS,
    PaymentMethod,
    Sale,
    SaleStatus,
    SALE_STATUS_LABELS,
)
from app.security.audit import log_action
from app.security.decorators import permission_required
from app.security.permissions import P
from app.services import sales as sales_service
from app.services.stock import dec

sales_bp = Blueprint("sales", __name__, url_prefix="/ventes")


def _can_view_all():
    return current_user.has_permission(P.SALES_VIEW_ALL)


def _load_sale(sale_id):
    sale = db.session.get(Sale, sale_id) or abort(404)
    if sale.vendeur_id != current_user.id and not _can_view_all():
        abort(403)
    return sale


@sales_bp.route("/")
@login_required
@permission_required(P.SALES_VIEW, mode="any")
def index():
    day = request.args.get("date")
    status = request.args.get("status")

    query = Sale.query
    if not _can_view_all():
        query = query.filter_by(vendeur_id=current_user.id)
    if day:
        try:
            start = datetime.strptime(day, "%Y-%m-%d")
        except ValueError:
            start = None
        if start:
            end = start.replace(hour=23, minute=59, second=59)
            query = query.filter(Sale.created_at >= start, Sale.created_at <= end)
    if status:
        query = query.filter_by(status=status)

    sales = query.order_by(Sale.created_at.desc()).limit(200).all()
    total_visible = sum((s.montant_total for s in sales if s.is_active), start=dec(0))
    return render_template(
        "sales/index.html",
        sales=sales,
        labels=SALE_STATUS_LABELS,
        day=day,
        status=status,
        total_visible=total_visible,
        can_view_all=_can_view_all(),
    )


@sales_bp.route("/<int:sale_id>")
@login_required
@permission_required(P.SALES_VIEW, mode="any")
def detail(sale_id):
    sale = _load_sale(sale_id)
    return render_template(
        "sales/detail.html",
        sale=sale,
        labels=SALE_STATUS_LABELS,
        payment_labels=PAYMENT_LABELS,
        methods=PaymentMethod,
    )


@sales_bp.route("/<int:sale_id>/annuler", methods=["POST"])
@login_required
@permission_required(P.SALES_CANCEL)
def cancel(sale_id):
    sale = db.session.get(Sale, sale_id) or abort(404)
    if sale.status != SaleStatus.VALIDEE:
        flash("Seule une vente validee peut etre annulee.", "danger")
        return redirect(url_for("sales.detail", sale_id=sale.id))

    reason = (request.form.get("reason") or "").strip()
    if not reason:
        flash("Le motif d'annulation est obligatoire.", "danger")
        return redirect(url_for("sales.detail", sale_id=sale.id))

    restock = bool(request.form.get("restock"))
    sales_service.cancel_sale(sale, current_user.id, reason, restock=restock)
    log_action(
        "sale_cancel",
        entity="sale",
        entity_uuid=sale.uuid,
        after={"numero": sale.numero, "restock": restock},
        reason=reason,
        commit=True,
    )
    flash(f"Vente {sale.numero} annulee.", "success")
    return redirect(url_for("sales.detail", sale_id=sale.id))


@sales_bp.route("/<int:sale_id>/rembourser", methods=["POST"])
@login_required
@permission_required(P.SALES_CANCEL)
def refund(sale_id):
    sale = db.session.get(Sale, sale_id) or abort(404)
    if sale.status not in (SaleStatus.VALIDEE, SaleStatus.REMBOURSEE):
        flash("Cette vente ne peut pas etre remboursee.", "danger")
        return redirect(url_for("sales.detail", sale_id=sale.id))

    amount = dec(request.form.get("amount"))
    motif = (request.form.get("motif") or "").strip()
    method = request.form.get("method") or PaymentMethod.ESPECE
    restock = bool(request.form.get("restock"))
    if amount <= 0:
        flash("Le montant a rembourser doit etre positif.", "danger")
        return redirect(url_for("sales.detail", sale_id=sale.id))
    if not motif:
        flash("Le motif du remboursement est obligatoire.", "danger")
        return redirect(url_for("sales.detail", sale_id=sale.id))

    try:
        sales_service.refund_sale(
            sale, current_user.id, amount, method, motif, restock=restock
        )
    except ValueError as exc:
        flash(str(exc), "danger")
        return redirect(url_for("sales.detail", sale_id=sale.id))

    log_action(
        "sale_refund",
        entity="sale",
        entity_uuid=sale.uuid,
        after={"numero": sale.numero, "amount": str(amount), "restock": restock},
        reason=motif,
        commit=True,
    )
    flash(f"Remboursement de {amount} enregistre.", "success")
    return redirect(url_for("sales.detail", sale_id=sale.id))
