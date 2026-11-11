"""Depenses : saisie, soumission, validation, rejet et categories."""
from flask import Blueprint, abort, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required
from sqlalchemy.exc import IntegrityError

from app.extensions import db
from app.models.finance import (
    EXPENSE_STATUS_LABELS,
    Expense,
    ExpenseCategory,
    ExpenseStatus,
)
from app.security.audit import log_action

from app.security.decorators import permission_required
from app.security.permissions import P
from app.services import cash as cash_service
from app.services import finance as finance_service
from app.services import settings as settings_service
from app.services.pagination import paginate
from app.services.stock import dec

expenses_bp = Blueprint("expenses", __name__, url_prefix="/depenses")

CURRENCIES = ("CDF", "USD")
EXPENSE_METHODS = {
    "espece": "Especes",
    "banque": "Banque / virement",
}


def _categories():
    return (
        ExpenseCategory.query.filter_by(active=True)
        .order_by(ExpenseCategory.name)
        .all()
    )


def _get_expense(expense_id):
    return db.session.get(Expense, expense_id) or abort(404)


@expenses_bp.route("/")
@login_required
@permission_required(P.EXPENSES_VIEW)
def index():
    status = (request.args.get("status") or "").strip()
    query = Expense.query
    if status in EXPENSE_STATUS_LABELS:
        query = query.filter_by(status=status)
    pager = paginate(query.order_by(Expense.expense_date.desc(), Expense.id.desc()))

    totals = {}
    status_counts = {
        ExpenseStatus.VALIDEE: 0,
        ExpenseStatus.ATTENTE: 0,
        ExpenseStatus.SAISIE: 0,
        ExpenseStatus.REJETEE: 0,
    }
    rows = (
        db.session.query(
            Expense.currency,
            Expense.status,
            db.func.coalesce(db.func.sum(Expense.amount), 0),
            db.func.count(Expense.id),
        )
        .group_by(Expense.currency, Expense.status)
        .all()
    )
    for currency, row_status, amount, count in rows:
        bucket = totals.setdefault(
            currency,
            {
                "validee": dec(0),
                "en_attente": dec(0),
                "saisie": dec(0),
                "rejetee": dec(0),
                "count": 0,
            },
        )
        bucket[row_status] = dec(amount)
        bucket["count"] += int(count or 0)
        status_counts[row_status] = status_counts.get(row_status, 0) + int(count or 0)

    return render_template(
        "expenses/index.html",
        expenses=pager.items,
        pager=pager,
        labels=EXPENSE_STATUS_LABELS,
        status=status,
        totals=totals,
        status_counts=status_counts,
        categories=_categories(),
        rate=settings_service.latest_rate(),
        methods=EXPENSE_METHODS,
    )


@expenses_bp.route("/nouvelle", methods=["GET", "POST"])
@login_required
@permission_required(P.EXPENSES_CREATE)
def new():
    categories = _categories()
    if request.method == "POST":
        try:
            amount = cash_service.money_value(request.form.get("amount"), "Le montant")
        except ValueError as exc:
            flash(str(exc), "danger")
            return render_template(
                "expenses/form.html",
                categories=categories,
                methods=EXPENSE_METHODS,
                currencies=CURRENCIES,
                form=request.form,
            )
        motif = (request.form.get("motif") or "").strip()
        if amount <= 0:
            flash("Le montant de la depense doit etre positif.", "danger")
            return render_template(
                "expenses/form.html",
                categories=categories,
                methods=EXPENSE_METHODS,
                currencies=CURRENCIES,
                form=request.form,
            )
        if not motif:
            flash("Le motif de la depense est obligatoire.", "danger")
            return render_template(
                "expenses/form.html",
                categories=categories,
                methods=EXPENSE_METHODS,
                currencies=CURRENCIES,
                form=request.form,
            )

        category_id = request.form.get("category_id", type=int)
        category = db.session.get(ExpenseCategory, category_id) if category_id else None
        method = request.form.get("method") or "espece"
        if method not in EXPENSE_METHODS:
            method = "espece"
        cash_session = (
            cash_service.find_open_session(vendeur_id=current_user.id)
            if method == "espece"
            else None
        )
        expense = finance_service.create_expense(
            user_id=current_user.id,
            amount=amount,
            currency=request.form.get("currency") or "CDF",
            motif=motif,
            category=category,
            beneficiary=(request.form.get("beneficiary") or "").strip() or None,
            method=method,
            cash_session=cash_session,
            notes=(request.form.get("notes") or "").strip() or None,
        )
        log_action(
            "expense_create",
            entity="expense",
            entity_uuid=expense.uuid,
            after={
                "reference": expense.reference,
                "amount": str(amount),
                "currency": expense.currency,
                "cash_session": cash_session.id if cash_session else None,
            },
            commit=True,
        )
        flash(f"Depense {expense.reference} enregistree en saisie.", "success")
        return redirect(url_for("expenses.detail", expense_id=expense.id))

    return render_template(
        "expenses/form.html",
        categories=categories,
        methods=EXPENSE_METHODS,
        currencies=CURRENCIES,
        form={},
    )


@expenses_bp.route("/<int:expense_id>")
@login_required
@permission_required(P.EXPENSES_VIEW)
def detail(expense_id):
    expense = _get_expense(expense_id)
    return render_template(
        "expenses/detail.html",
        expense=expense,
        labels=EXPENSE_STATUS_LABELS,
        methods=EXPENSE_METHODS,
        rate=settings_service.latest_rate(),
    )


@expenses_bp.route("/<int:expense_id>/soumettre", methods=["POST"])
@login_required
@permission_required(P.EXPENSES_CREATE)
def submit(expense_id):
    expense = _get_expense(expense_id)
    if expense.status not in (ExpenseStatus.SAISIE, ExpenseStatus.REJETEE):
        flash("Cette depense ne peut pas etre soumise dans son etat actuel.", "warning")
        return redirect(url_for("expenses.detail", expense_id=expense.id))
    finance_service.submit_expense(expense)
    log_action(
        "expense_submit",
        entity="expense",
        entity_uuid=expense.uuid,
        after={"reference": expense.reference, "status": expense.status},
        commit=True,
    )
    flash("Depense soumise pour validation.", "success")
    return redirect(url_for("expenses.detail", expense_id=expense.id))


@expenses_bp.route("/<int:expense_id>/valider", methods=["POST"])
@login_required
@permission_required(P.EXPENSES_VALIDATE)
def validate(expense_id):
    expense = _get_expense(expense_id)
    if expense.status == ExpenseStatus.VALIDEE:
        flash("Cette depense est deja validee.", "warning")
        return redirect(url_for("expenses.detail", expense_id=expense.id))
    if expense.status == ExpenseStatus.REJETEE:
        flash("Une depense rejetee doit etre soumise a nouveau avant validation.", "warning")
        return redirect(url_for("expenses.detail", expense_id=expense.id))

    # Rattache une caisse ouverte au moment de la validation si la depense
    # n'en avait pas (saisie par un profil sans caisse ou caisse depuis fermee).
    if expense.method == "espece" and (
        expense.cash_session is None or not expense.cash_session.is_open
    ):
        session = cash_service.find_open_session(vendeur_id=current_user.id)
        if session is not None:
            expense.cash_session = session

    cash_linked = (
        expense.method == "espece"
        and expense.cash_session is not None
        and expense.cash_session.is_open
    )
    try:
        finance_service.validate_expense(expense, current_user.id)
    except ValueError as exc:
        db.session.rollback()
        flash(str(exc), "danger")
        return redirect(url_for("expenses.detail", expense_id=expense.id))

    log_action(
        "expense_validate",
        entity="expense",
        entity_uuid=expense.uuid,
        after={
            "reference": expense.reference,
            "amount": str(expense.amount),
            "cash_session": expense.cash_session_id,
        },
        commit=True,
    )
    if cash_linked:
        flash("Depense validee et deduite de la caisse.", "success")
    else:
        flash(
            "Depense validee. Aucune caisse espece ouverte : aucune deduction "
            "de caisse n'a ete effectuee.",
            "warning",
        )
    return redirect(url_for("expenses.detail", expense_id=expense.id))


@expenses_bp.route("/<int:expense_id>/rejeter", methods=["POST"])
@login_required
@permission_required(P.EXPENSES_VALIDATE)
def reject(expense_id):
    expense = _get_expense(expense_id)
    reason = (request.form.get("reason") or "").strip()
    if not reason:
        flash("Le motif du rejet est obligatoire.", "danger")
        return redirect(url_for("expenses.detail", expense_id=expense.id))
    if expense.status == ExpenseStatus.VALIDEE:
        flash("Une depense validee ne peut pas etre rejetee.", "warning")
        return redirect(url_for("expenses.detail", expense_id=expense.id))
    finance_service.reject_expense(expense, current_user.id, reason)
    log_action(
        "expense_reject",
        entity="expense",
        entity_uuid=expense.uuid,
        after={"reference": expense.reference},
        reason=reason,
        commit=True,
    )
    flash("Depense rejetee.", "success")
    return redirect(url_for("expenses.detail", expense_id=expense.id))


@expenses_bp.route("/categories", methods=["POST"])
@login_required
@permission_required(P.EXPENSES_VALIDATE)
def add_category():
    name = (request.form.get("name") or "").strip()
    if not name:
        flash("Le nom de la categorie est obligatoire.", "danger")
        return redirect(url_for("expenses.index"))
    existing = ExpenseCategory.query.filter(
        db.func.lower(ExpenseCategory.name) == name.lower()
    ).first()
    if existing is not None:
        flash("Cette categorie existe deja.", "warning")
        return redirect(url_for("expenses.index"))
    db.session.add(ExpenseCategory(name=name))
    try:
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        flash("Cette categorie existe deja.", "warning")
        return redirect(url_for("expenses.index"))
    log_action(
        "expense_category_create",
        entity="expense_category",
        after={"name": name},
        commit=True,
    )
    flash("Categorie ajoutee.", "success")
    return redirect(url_for("expenses.index"))
