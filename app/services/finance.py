"""Logique finance : depenses, credits (clients/fournisseurs), echeances et reglements."""
from datetime import date, timedelta
from decimal import Decimal

from app.extensions import db
from app.models.base import utcnow
from app.models.finance import (
    Credit,
    CreditStatus,
    CreditType,
    Expense,
    ExpenseStatus,
    Installment,
    InstallmentStatus,
    Settlement,
)
from app.models.sales import CashMovementKind
from app.services import cash as cash_service
from app.services.stock import dec


# ---------------------------------------------------------------- Depenses
def next_expense_reference(day=None):
    day = day or date.today()
    prefix = f"D-{day:%Y%m%d}"
    count = Expense.query.filter(Expense.reference.like(prefix + "%")).count()
    return f"{prefix}-{count + 1:04d}"


def create_expense(
    *,
    user_id,
    amount,
    currency,
    motif,
    category=None,
    beneficiary=None,
    method="espece",
    cash_session=None,
    notes=None,
    commit=True,
):
    expense = Expense(
        reference=next_expense_reference(),
        expense_date=utcnow(),
        amount=dec(amount),
        currency=currency,
        category_id=category.id if category else None,
        motif=motif,
        beneficiary=beneficiary,
        method=method,
        status=ExpenseStatus.SAISIE,
        cash_session_id=cash_session.id if cash_session else None,
        created_by_id=user_id,
        notes=notes,
    )
    db.session.add(expense)
    if commit:
        db.session.commit()
    return expense


def submit_expense(expense, commit=True):
    expense.status = ExpenseStatus.ATTENTE
    if commit:
        db.session.commit()
    return expense


def validate_expense(expense, user_id, commit=True):
    """Valide une depense ; deduit la caisse si un tiroir est ouvert et paiement espece."""
    session = expense.cash_session
    if session is not None and session.is_open and expense.method == "espece":
        cash_service.record_cash(
            session,
            CashMovementKind.DEPENSE,
            -dec(expense.amount),
            source_type="expense",
            source_uuid=expense.uuid,
            reason=f"Depense {expense.reference}",
            user_id=user_id,
            commit=False,
        )
    expense.status = ExpenseStatus.VALIDEE
    expense.validated_by_id = user_id
    expense.validated_at = utcnow()
    if commit:
        db.session.commit()
    return expense


def reject_expense(expense, user_id, reason, commit=True):
    expense.status = ExpenseStatus.REJETEE
    expense.validated_by_id = user_id
    expense.validated_at = utcnow()
    expense.reject_reason = (reason or "").strip() or None
    if commit:
        db.session.commit()
    return expense


# ---------------------------------------------------------------- Credits
def create_credit(
    *,
    credit_type,
    amount,
    currency,
    customer=None,
    supplier=None,
    due_date=None,
    sale=None,
    installments=None,
    notes=None,
    user_id=None,
    commit=True,
):
    amount = dec(amount)
    credit = Credit(
        type=credit_type,
        customer_id=customer.id if customer else None,
        supplier_id=supplier.id if supplier else None,
        amount_initial=amount,
        amount_remaining=amount,
        currency=currency,
        status=CreditStatus.ACTIF,
        due_date=due_date,
        sale_id=sale.id if sale else None,
        notes=notes,
        created_by_id=user_id,
    )
    db.session.add(credit)
    db.session.flush()

    for inst in installments or []:
        due = inst.get("due_date")
        amount_due = dec(inst.get("amount_due"))
        if due is None or amount_due <= 0:
            continue
        db.session.add(
            Installment(credit_id=credit.id, due_date=due, amount_due=amount_due)
        )

    refresh_credit_status(credit)
    refresh_installments(credit)
    if commit:
        db.session.commit()
    return credit


def add_settlement(
    credit,
    *,
    amount,
    method="espece",
    user_id=None,
    cash_session=None,
    reference=None,
    commit=True,
):
    """Enregistre un reglement et met a jour le solde, le statut et la caisse."""
    amount = dec(amount)
    if amount <= 0:
        raise ValueError("Le montant du reglement doit etre positif.")
    if amount > dec(credit.amount_remaining):
        raise ValueError("Le reglement depasse le solde restant.")

    settlement = Settlement(
        credit_id=credit.id,
        amount=amount,
        currency=credit.currency,
        method=method,
        reference=(reference or "").strip() or None,
        cash_session_id=cash_session.id if cash_session else None,
        user_id=user_id,
    )
    db.session.add(settlement)
    db.session.flush()

    credit.amount_remaining = dec(credit.amount_remaining) - amount

    if cash_session is not None and method == "espece":
        if credit.is_client:
            kind, signed = CashMovementKind.RECOUVREMENT, amount
        else:
            kind, signed = CashMovementKind.REGLEMENT, -amount
        cash_service.record_cash(
            cash_session,
            kind,
            signed,
            source_type="settlement",
            source_uuid=settlement.uuid,
            reason=f"Reglement credit {credit.partner_name}",
            user_id=user_id,
            commit=False,
        )

    refresh_credit_status(credit)
    refresh_installments(credit)
    if commit:
        db.session.commit()
    return settlement


def refresh_credit_status(credit):
    remaining = dec(credit.amount_remaining)
    initial = dec(credit.amount_initial)
    if remaining <= 0:
        credit.amount_remaining = Decimal("0")
        credit.status = CreditStatus.SOLDE
    elif remaining < initial:
        credit.status = CreditStatus.PARTIEL
    else:
        credit.status = CreditStatus.ACTIF

    if credit.status != CreditStatus.SOLDE and credit.due_date and credit.due_date < date.today():
        credit.status = CreditStatus.EN_RETARD
    return credit.status


def refresh_installments(credit):
    today = date.today()
    paid = dec(credit.settled_total)
    cumulative = Decimal("0")
    for inst in credit.installments:
        cumulative += dec(inst.amount_due)
        if paid >= cumulative:
            inst.status = InstallmentStatus.PAYEE
        elif inst.due_date and inst.due_date < today:
            inst.status = InstallmentStatus.ECHUE
        else:
            inst.status = InstallmentStatus.A_VENIR
    return credit.installments


def refresh_all_credit_statuses(commit=True):
    for credit in Credit.query.all():
        refresh_credit_status(credit)
        refresh_installments(credit)
    if commit:
        db.session.commit()


# ---------------------------------------------------------------- Alertes
def credit_alerts(horizon_days=7):
    """Echeances de credit a surveiller : en retard + echeances proches.

    Retourne (credits_en_retard, echeances_proches). Les credits soldes sont exclus.
    """
    today = date.today()
    horizon = today + timedelta(days=horizon_days)

    open_credits = Credit.query.filter(Credit.status != CreditStatus.SOLDE).all()
    en_retard = [c for c in open_credits if c.due_date and c.due_date < today]
    # Ne pas compter deux fois : un credit en retard n'est pas aussi "proche"
    proches = [
        c for c in open_credits
        if c.due_date and today <= c.due_date <= horizon
    ]

    # Echeances (installments) echues non payees
    echeances_echues = (
        Installment.query.filter(
            Installment.status == InstallmentStatus.ECHUE,
            Installment.due_date < today,
        )
        .order_by(Installment.due_date)
        .all()
    )
    return en_retard, proches, echeances_echues
