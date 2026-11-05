"""Partenaires : clients et fournisseurs."""
from flask import Blueprint, abort, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required

from app.extensions import db
from app.models.finance import Credit
from app.models.partners import Customer, Supplier
from app.models.purchases import Purchase
from app.models.stock import StockEntryRequest
from app.security.audit import log_action
from app.security.decorators import admin_password_required, permission_required
from app.security.permissions import P
from app.services.pagination import paginate
from app.services.stock import dec

partners_bp = Blueprint("partners", __name__, url_prefix="/partenaires")

CURRENCIES = ("CDF", "USD")


@partners_bp.route("/clients", methods=["GET", "POST"])
@login_required
@permission_required(P.PARTNERS_VIEW)
def customers():
    if request.method == "POST":
        if not current_user.has_permission(P.PARTNERS_MANAGE):
            abort(403)
        name = (request.form.get("name") or "").strip()
        if not name:
            flash("Le nom du client est obligatoire.", "danger")
        elif Customer.query.filter_by(name=name).first():
            flash("Ce client existe deja.", "danger")
        else:
            customer = Customer(
                name=name,
                contact=(request.form.get("contact") or "").strip() or None,
                credit_limit=dec(request.form.get("credit_limit")),
            )
            db.session.add(customer)
            log_action("customer_create", entity="customer", after={"name": name}, commit=True)
            flash(f"Client « {name} » cree.", "success")
        return redirect(url_for("partners.customers"))

    pager = paginate(Customer.query.order_by(Customer.name))
    return render_template(
        "partners/customers.html",
        customers=pager.items,
        pager=pager,
    )


@partners_bp.route("/clients/<int:customer_id>/supprimer", methods=["POST"])
@login_required
@permission_required(P.PARTNERS_MANAGE)
@admin_password_required()
def delete_customer(customer_id):
    customer = db.session.get(Customer, customer_id) or abort(404)
    used = Credit.query.filter_by(customer_id=customer.id).count()
    if used:
        flash(f"Client « {customer.name} » a {used} crédit(s) : suppression refusée (désactivez-le plutôt).", "danger")
        return redirect(url_for("partners.customers"))
    name = customer.name
    db.session.delete(customer)
    log_action("customer_delete", entity="customer", after={"name": name}, commit=True)
    flash(f"Client « {name} » supprimé.", "success")
    return redirect(url_for("partners.customers"))


@partners_bp.route("/clients/<int:customer_id>/modifier", methods=["GET", "POST"])
@login_required
@permission_required(P.PARTNERS_MANAGE)
def edit_customer(customer_id):
    customer = db.session.get(Customer, customer_id) or abort(404)
    if request.method == "POST":
        name = (request.form.get("name") or "").strip()
        if not name:
            flash("Le nom est obligatoire.", "danger")
            return redirect(url_for("partners.edit_customer", customer_id=customer.id))
        customer.name = name
        customer.contact = (request.form.get("contact") or "").strip() or None
        customer.credit_limit = dec(request.form.get("credit_limit"))
        customer.active = bool(request.form.get("active"))
        customer.notes = (request.form.get("notes") or "").strip() or None
        log_action("customer_update", entity="customer", entity_uuid=customer.uuid, after={"name": name}, commit=True)
        flash("Client mis a jour.", "success")
        return redirect(url_for("partners.customers"))
    return render_template("partners/customer_form.html", customer=customer)


@partners_bp.route("/fournisseurs", methods=["GET", "POST"])
@login_required
@permission_required(P.PARTNERS_VIEW)
def suppliers():
    if request.method == "POST":
        if not current_user.has_permission(P.PARTNERS_MANAGE):
            abort(403)
        name = (request.form.get("name") or "").strip()
        if not name:
            flash("Le nom du fournisseur est obligatoire.", "danger")
        elif Supplier.query.filter_by(name=name).first():
            flash("Ce fournisseur existe deja.", "danger")
        else:
            supplier = Supplier(
                name=name,
                contact=(request.form.get("contact") or "").strip() or None,
                default_currency=request.form.get("default_currency") or "CDF",
                terms=(request.form.get("terms") or "").strip() or None,
            )
            db.session.add(supplier)
            log_action("supplier_create", entity="supplier", after={"name": name}, commit=True)
            flash(f"Fournisseur « {name} » cree.", "success")
        return redirect(url_for("partners.suppliers"))

    pager = paginate(Supplier.query.order_by(Supplier.name))
    return render_template(
        "partners/suppliers.html",
        suppliers=pager.items,
        pager=pager,
        currencies=CURRENCIES,
    )


@partners_bp.route("/fournisseurs/<int:supplier_id>/supprimer", methods=["POST"])
@login_required
@permission_required(P.PARTNERS_MANAGE)
@admin_password_required()
def delete_supplier(supplier_id):
    supplier = db.session.get(Supplier, supplier_id) or abort(404)
    used = (
        Purchase.query.filter_by(supplier_id=supplier.id).count()
        + Credit.query.filter_by(supplier_id=supplier.id).count()
        + StockEntryRequest.query.filter_by(supplier_id=supplier.id).count()
    )
    if used:
        flash(f"Fournisseur « {supplier.name} » a {used} opération(s) liée(s) : suppression refusée (désactivez-le plutôt).", "danger")
        return redirect(url_for("partners.suppliers"))
    name = supplier.name
    db.session.delete(supplier)
    log_action("supplier_delete", entity="supplier", after={"name": name}, commit=True)
    flash(f"Fournisseur « {name} » supprimé.", "success")
    return redirect(url_for("partners.suppliers"))


@partners_bp.route("/fournisseurs/<int:supplier_id>/modifier", methods=["GET", "POST"])
@login_required
@permission_required(P.PARTNERS_MANAGE)
def edit_supplier(supplier_id):
    supplier = db.session.get(Supplier, supplier_id) or abort(404)
    if request.method == "POST":
        name = (request.form.get("name") or "").strip()
        if not name:
            flash("Le nom est obligatoire.", "danger")
            return redirect(url_for("partners.edit_supplier", supplier_id=supplier.id))
        supplier.name = name
        supplier.contact = (request.form.get("contact") or "").strip() or None
        supplier.default_currency = request.form.get("default_currency") or "CDF"
        supplier.terms = (request.form.get("terms") or "").strip() or None
        supplier.active = bool(request.form.get("active"))
        supplier.notes = (request.form.get("notes") or "").strip() or None
        log_action("supplier_update", entity="supplier", entity_uuid=supplier.uuid, after={"name": name}, commit=True)
        flash("Fournisseur mis a jour.", "success")
        return redirect(url_for("partners.suppliers"))
    return render_template("partners/supplier_form.html", supplier=supplier, currencies=CURRENCIES)
