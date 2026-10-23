"""Credits : creances clients et dettes fournisseurs, echeances et reglements."""
from datetime import datetime

from flask import Blueprint, abort, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required

from app.extensions import db
from app.models.finance import (
    CREDIT_STATUS_LABELS,
    CREDIT_TYPE_LABELS,
    INSTALLMENT_STATUS_LABELS,
    Credit,
    CreditType,
)
from app.models.partners import Customer, Supplier
from app.models.sales import PAYMENT_LABELS, PaymentMethod
from app.security.audit import log_action
from app.security.decorators import permission_required
from app.security.permissions import P
from app.services import cash as cash_service
from app.services import finance as finance_service
from app.services.stock import dec

credits_bp = Blueprint("credits", __name__, url_prefix="/credits")

CURRENCIES = ("CDF", "USD")


def _parse_date(value):
    value = (value or "").strip()
    if not value:
        return None
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except ValueError:
        return None


def _installments_from_form():
    dates = request.form.getlist("inst_due")
    amounts = request.form.getlist("inst_amount")
    result = []
    for due, amount in zip(dates, amounts):
        due_date = _parse_date(due)
        amount_due = dec(amount)
        if due_date is not None and amount_due > 0:
            result.append({"due_date": due_date, "amount_due": amount_due})
    return result


@credits_bp.route("/")
@login_required
@permission_required(P.CREDITS_VIEW)
def index():
    credit_type = request.args.get("type")
    status = request.args.get("status")
    query = Credit.query
    if credit_type:
        query = query.filter_by(type=credit_type)
    if status:
        query = query.filter_by(status=status)
    credits = query.order_by(Credit.created_at.desc()).limit(200).all()

    en_cours = [c for c in credits if c.status != "solde"]
    total_client = sum((c.amount_remaining for c in en_cours if c.is_client), start=dec(0))
    total_fournisseur = sum((c.amount_remaining for c in en_cours if not c.is_client), start=dec(0))

    return render_template(
        "credits/index.html",
        credits=credits,
        type_labels=CREDIT_TYPE_LABELS,
        status_labels=CREDIT_STATUS_LABELS,
        credit_type=credit_type,
        status=status,
        total_client=total_client,
        total_fournisseur=total_fournisseur,
    )


@credits_bp.route("/client/nouveau", methods=["GET", "POST"])
@login_required
@permission_required(P.CREDITS_MANAGE)
def new_client():
    if request.method == "POST":
        customer = db.session.get(Customer, request.form.get("customer_id", type=int))
        amount = dec(request.form.get("amount"))
        if customer is None or amount <= 0:
            flash("Client et montant valides obligatoires.", "danger")
            return redirect(url_for("credits.new_client"))

        credit = finance_service.create_credit(
            credit_type=CreditType.CLIENT,
            amount=amount,
            currency=request.form.get("currency") or "CDF",
            customer=customer,
            due_date=_parse_date(request.form.get("due_date")),
            installments=_installments_from_form(),
            notes=(request.form.get("notes") or "").strip() or None,
            user_id=current_user.id,
        )
        log_action("credit_create", entity="credit", entity_uuid=credit.uuid, after={"type": "client", "amount": str(amount)}, commit=True)
        flash(f"Creance client creee pour {customer.name}.", "success")
        return redirect(url_for("credits.detail", credit_id=credit.id))

    return render_template(
        "credits/form.html",
        credit_type=CreditType.CLIENT,
        type_label=CREDIT_TYPE_LABELS[CreditType.CLIENT],
        customers=Customer.query.filter_by(active=True).order_by(Customer.name).all(),
        suppliers=[],
        currencies=CURRENCIES,
    )


@credits_bp.route("/fournisseur/nouveau", methods=["GET", "POST"])
@login_required
@permission_required(P.CREDITS_MANAGE)
def new_supplier():
    if request.method == "POST":
        supplier = db.session.get(Supplier, request.form.get("supplier_id", type=int))
        amount = dec(request.form.get("amount"))
        if supplier is None or amount <= 0:
            flash("Fournisseur et montant valides obligatoires.", "danger")
            return redirect(url_for("credits.new_supplier"))

        credit = finance_service.create_credit(
            credit_type=CreditType.FOURNISSEUR,
            amount=amount,
            currency=request.form.get("currency") or "CDF",
            supplier=supplier,
            due_date=_parse_date(request.form.get("due_date")),
            installments=_installments_from_form(),
            notes=(request.form.get("notes") or "").strip() or None,
            user_id=current_user.id,
        )
        log_action("credit_create", entity="credit", entity_uuid=credit.uuid, after={"type": "fournisseur", "amount": str(amount)}, commit=True)
        flash(f"Dette fournisseur creee pour {supplier.name}.", "success")
        return redirect(url_for("credits.detail", credit_id=credit.id))

    return render_template(
        "credits/form.html",
        credit_type=CreditType.FOURNISSEUR,
        type_label=CREDIT_TYPE_LABELS[CreditType.FOURNISSEUR],
        customers=[],
        suppliers=Supplier.query.filter_by(active=True).order_by(Supplier.name).all(),
        currencies=CURRENCIES,
    )


@credits_bp.route("/<int:credit_id>")
@login_required
@permission_required(P.CREDITS_VIEW)
def detail(credit_id):
    credit = db.session.get(Credit, credit_id) or abort(404)
    return render_template(
        "credits/detail.html",
        credit=credit,
        type_labels=CREDIT_TYPE_LABELS,
        status_labels=CREDIT_STATUS_LABELS,
        installment_labels=INSTALLMENT_STATUS_LABELS,
        methods=PAYMENT_LABELS,
    )


@credits_bp.route("/<int:credit_id>/regler", methods=["POST"])
@login_required
@permission_required(P.CREDITS_MANAGE)
def settle(credit_id):
    credit = db.session.get(Credit, credit_id) or abort(404)
    amount = dec(request.form.get("amount"))
    method = request.form.get("method") or PaymentMethod.ESPECE
    session = cash_service.find_open_session(vendeur_id=current_user.id)
    try:
        settlement = finance_service.add_settlement(
            credit,
            amount=amount,
            method=method,
            user_id=current_user.id,
            cash_session=session,
            reference=request.form.get("reference"),
        )
    except ValueError as exc:
        flash(str(exc), "danger")
        return redirect(url_for("credits.detail", credit_id=credit.id))

    log_action("credit_settle", entity="credit", entity_uuid=credit.uuid, after={"amount": str(amount), "remaining": str(credit.amount_remaining)}, commit=True)
    flash("Reglement enregistre.", "success")
    _ = settlement
    return redirect(url_for("credits.detail", credit_id=credit.id))


@credits_bp.route("/<int:credit_id>/echeance", methods=["POST"])
@login_required
@permission_required(P.CREDITS_MANAGE)
def add_installment(credit_id):
    credit = db.session.get(Credit, credit_id) or abort(404)
    due_date = _parse_date(request.form.get("due_date"))
    amount_due = dec(request.form.get("amount_due"))
    if due_date is None or amount_due <= 0:
        flash("Echeance invalide.", "danger")
    else:
        from app.models.finance import Installment

        db.session.add(Installment(credit_id=credit.id, due_date=due_date, amount_due=amount_due))
        finance_service.refresh_installments(credit)
        log_action("credit_installment_add", entity="credit", entity_uuid=credit.uuid, after={"due_date": str(due_date), "amount": str(amount_due)}, commit=True)
        flash("Echeance ajoutee.", "success")
    return redirect(url_for("credits.detail", credit_id=credit.id))
