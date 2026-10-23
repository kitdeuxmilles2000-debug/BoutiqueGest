"""Depenses : saisie, soumission, validation / rejet."""
from flask import Blueprint, abort, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required

from app.extensions import db
from app.models.finance import EXPENSE_STATUS_LABELS, Expense, ExpenseCategory, ExpenseStatus
from app.models.sales import PAYMENT_LABELS, PaymentMethod
from app.security.audit import log_action
from app.security.decorators import permission_required
from app.security.permissions import P
from app.services import cash as cash_service
from app.services import finance as finance_service
from app.services.stock import dec

expenses_bp = Blueprint("expenses", __name__, url_prefix="/depenses")


def _categories():
    return ExpenseCategory.query.order_by(ExpenseCategory.name).all()


@expenses_bp.route("/")
@login_required
@permission_required(P.EXPENSES_VIEW)
def index():
    status = request.args.get("status")
    query = Expense.query
    if status:
        query = query.filter_by(status=status)
    expenses = query.order_by(Expense.expense_date.desc()).limit(200).all()
    return render_template(
        "expenses/index.html",
        expenses=expenses,
        labels=EXPENSE_STATUS_LABELS,
        status=status,
        categories=_categories(),
        methods=PAYMENT_LABELS,
    )


@expenses_bp.route("/nouvelle", methods=["GET", "POST"])
@login_required
@permission_required(P.EXPENSES_CREATE)
def new():
    if request.method == "POST":
        amount = dec(request.form.get("amount"))
        motif = (request.form.get("motif") or "").strip()
        currency = request.form.get("currency") or "CDF"
        if amount <= 0:
            flash("Le montant doit etre positif.", "danger")
            return redirect(url_for("expenses.new"))
        if not motif:
            flash("Le motif est obligatoire.", "danger")
            return redirect(url_for("expenses.new"))

        category_id = request.form.get("category_id", type=int)
        category = db.session.get(ExpenseCategory, category_id) if category_id else None
        session = cash_service.find_open_session(vendeur_id=current_user.id)
        expense = finance_service.create_expense(
            user_id=current_user.id,
            amount=amount,
            currency=currency,
            motif=motif,
            category=category,
            beneficiary=(request.form.get("beneficiary") or "").strip() or None,
            method=request.form.get("method") or PaymentMethod.ESPECE,
            cash_session=session,
            notes=(request.form.get("notes") or "").strip() or None,
        )
        log_action("expense_create", entity="expense", entity_uuid=expense.uuid, after={"reference": expense.reference, "amount": str(amount)}, commit=True)
        flash(f"Depense {expense.reference} enregistree (saisie).", "success")
        return redirect(url_for("expenses.detail", expense_id=expense.id))

    return render_template(
        "expenses/form.html",
        categories=_categories(),
        methods=PAYMENT_LABELS,
    )


@expenses_bp.route("/<int:expense_id>")
@login_required
@permission_required(P.EXPENSES_VIEW)
def detail(expense_id):
    expense = db.session.get(Expense, expense_id) or abort(404)
    return render_template("expenses/detail.html", expense=expense, labels=EXPENSE_STATUS_LABELS, methods=PAYMENT_LABELS)


@expenses_bp.route("/<int:expense_id>/soumettre", methods=["POST"])
@login_required
@permission_required(P.EXPENSES_CREATE)
def submit(expense_id):
    expense = db.session.get(Expense, expense_id) or abort(404)
    if expense.status not in (ExpenseStatus.SAISIE, ExpenseStatus.REJETEE):
        flash("Cette depense ne peut pas etre soumise.", "danger")
        return redirect(url_for("expenses.detail", expense_id=expense.id))
    finance_service.submit_expense(expense)
    log_action("expense_submit", entity="expense", entity_uuid=expense.uuid, commit=True)
    flash("Depense soumise pour validation.", "success")
    return redirect(url_for("expenses.detail", expense_id=expense.id))


@expenses_bp.route("/<int:expense_id>/valider", methods=["POST"])
@login_required
@permission_required(P.EXPENSES_VALIDATE)
def validate(expense_id):
    expense = db.session.get(Expense, expense_id) or abort(404)
    if expense.status == ExpenseStatus.VALIDEE:
        flash("Cette depense est deja validee.", "warning")
        return redirect(url_for("expenses.detail", expense_id=expense.id))
    finance_service.validate_expense(expense, current_user.id)
    log_action("expense_validate", entity="expense", entity_uuid=expense.uuid, after={"amount": str(expense.amount)}, commit=True)
    flash("Depense validee.", "success")
    return redirect(url_for("expenses.detail", expense_id=expense.id))


@expenses_bp.route("/<int:expense_id>/rejeter", methods=["POST"])
@login_required
@permission_required(P.EXPENSES_VALIDATE)
def reject(expense_id):
    expense = db.session.get(Expense, expense_id) or abort(404)
    reason = (request.form.get("reason") or "").strip()
    if not reason:
        flash("Le motif de rejet est obligatoire.", "danger")
        return redirect(url_for("expenses.detail", expense_id=expense.id))
    finance_service.reject_expense(expense, current_user.id, reason)
    log_action("expense_reject", entity="expense", entity_uuid=expense.uuid, reason=reason, commit=True)
    flash("Depense rejetee.", "success")
    return redirect(url_for("expenses.detail", expense_id=expense.id))


@expenses_bp.route("/categories", methods=["POST"])
@login_required
@permission_required(P.EXPENSES_VALIDATE)
def add_category():
    name = (request.form.get("name") or "").strip()
    if not name:
        flash("Nom de categorie obligatoire.", "danger")
    elif ExpenseCategory.query.filter_by(name=name).first():
        flash("Cette categorie existe deja.", "danger")
    else:
        db.session.add(ExpenseCategory(name=name))
        log_action("expense_category_create", entity="expense_category", after={"name": name}, commit=True)
        flash(f"Categorie « {name} » creee.", "success")
    return redirect(url_for("expenses.index"))
