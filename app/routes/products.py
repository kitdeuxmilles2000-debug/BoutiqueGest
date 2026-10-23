"""Catalogue : produits, unites de vente, categories."""
from flask import Blueprint, abort, flash, redirect, render_template, request, url_for
from flask_login import login_required
from decimal import Decimal

from app.extensions import db
from app.models.catalog import (
    Category,
    PriceHistory,
    PriceKind,
    Product,
    ProductKind,
    ProductUnit,
    Unit,
)
from app.models.stock import Batch, StockEntryRequest, StockEntryStatus
from app.security.audit import log_action
from app.security.decorators import permission_required
from app.security.permissions import P
from app.services.stock import dec, product_movements
products_bp = Blueprint("products", __name__, url_prefix="/produits")

CURRENCIES = ("CDF", "USD")


def _units():
    return Unit.query.order_by(Unit.label).all()


def _categories():
    return Category.query.order_by(Category.name).all()


@products_bp.route("/")
@login_required
@permission_required(P.PRODUCTS_VIEW)
def index():
    search = (request.args.get("q") or "").strip()
    category_id = request.args.get("category", type=int)
    alert = request.args.get("alert")

    query = Product.query
    if search:
        like = f"%{search}%"
        query = query.filter(db.or_(Product.name.ilike(like), Product.code.ilike(like)))
    if category_id:
        query = query.filter(Product.category_id == category_id)

    products = query.order_by(Product.name).all()
    if alert == "low":
        products = [p for p in products if p.is_low_stock or p.is_out_of_stock]

    # Quantites en attente de validation (entrees non validees par le proprietaire)
    from app.models.stock import StockEntryRequest, StockEntryStatus

    pending_rows = (
        db.session.query(StockEntryRequest.product_id, db.func.sum(StockEntryRequest.qty_base))
        .filter(StockEntryRequest.status == StockEntryStatus.EN_ATTENTE)
        .group_by(StockEntryRequest.product_id)
        .all()
    )
    pending_qty = {pid: (qty or dec(0)) for pid, qty in pending_rows}

    return render_template(
        "products/index.html",
        products=products,
        categories=_categories(),
        search=search,
        category_id=category_id,
        alert=alert,
        pending_qty=pending_qty,
    )


@products_bp.route("/nouveau", methods=["GET", "POST"])
@login_required
@permission_required(P.PRODUCTS_MANAGE)
def new():
    if request.method == "POST":
        return _save_product(None)
    return render_template(
        "products/form.html",
        product=None,
        units=_units(),
        categories=_categories(),
        kinds=ProductKind,
        currencies=CURRENCIES,
        base_prix=None,
        units_hors_base=[],
        batches=[],
    )


@products_bp.route("/<int:product_id>/modifier", methods=["GET", "POST"])
@login_required
@permission_required(P.PRODUCTS_MANAGE)
def edit(product_id):
    product = db.session.get(Product, product_id) or abort(404)
    if request.method == "POST":
        return _save_product(product)
    base_pu = ProductUnit.query.filter_by(
        product_id=product.id, unit_id=product.base_unit_id
    ).first()
    hors_base = [pu for pu in product.selling_units if pu.unit_id != product.base_unit_id]
    batches = (
        Batch.query.filter_by(product_id=product.id, active=True)
        .order_by(Batch.expiry_date.is_(None), Batch.expiry_date.asc())
        .all()
    )
    return render_template(
        "products/form.html",
        product=product,
        units=_units(),
        categories=_categories(),
        kinds=ProductKind,
        currencies=CURRENCIES,
        base_prix=base_pu.prix_vente if base_pu else None,
        units_hors_base=hors_base,
        batches=batches,
    )


def _next_product_code():
    from app.models.base import utcnow
    today = utcnow().strftime("%y%m%d")
    count = Product.query.count() + 1
    return f"PRD-{today}-{count:04d}"


def _set_base_price(product, prix, currency):
    """Enregistre le prix de vente de l'unite de base (factor 1)."""
    if prix <= 0:
        return
    pu = ProductUnit.query.filter_by(
        product_id=product.id, unit_id=product.base_unit_id
    ).first()
    if pu is None:
        pu = ProductUnit(
            product_id=product.id,
            unit_id=product.base_unit_id,
            factor=Decimal("1"),
            prix_vente=prix,
            currency=currency,
            is_sale_default=not ProductUnit.query.filter_by(
                product_id=product.id, is_sale_default=True
            ).count(),
        )
        db.session.add(pu)
    else:
        changed = pu.prix_vente != prix
        pu.prix_vente = prix
        pu.currency = currency
        if changed:
            db.session.add(
                PriceHistory(
                    product_id=product.id,
                    kind=PriceKind.VENTE,
                    prix=prix,
                    currency=currency,
                )
            )
    db.session.flush()


def _set_selling_unit(product, unit_id, factor, prix, currency, is_default):
    """Cree ou met a jour une unite de vente secondaire."""
    pu = ProductUnit.query.filter_by(product_id=product.id, unit_id=unit_id).first()
    if pu is None:
        pu = ProductUnit(
            product_id=product.id,
            unit_id=unit_id,
            factor=factor,
            prix_vente=prix,
            currency=currency,
            is_sale_default=is_default,
        )
        db.session.add(pu)
    else:
        pu.factor = factor
        changed = pu.prix_vente != prix
        pu.prix_vente = prix
        pu.currency = currency
        if changed:
            db.session.add(
                PriceHistory(
                    product_id=product.id,
                    kind=PriceKind.VENTE,
                    prix=prix,
                    currency=currency,
                )
            )
    if is_default:
        ProductUnit.query.filter_by(product_id=product.id).update(
            {"is_sale_default": False}
        )
        pu.is_sale_default = True
    db.session.flush()
    return pu


def _save_product(product):
    code = (request.form.get("code") or "").strip().upper()
    name = (request.form.get("name") or "").strip()
    base_unit_id = request.form.get("base_unit_id", type=int)
    category_id = request.form.get("category_id", type=int)
    currency = request.form.get("currency") or "CDF"
    kind = request.form.get("kind") or ProductKind.AUTRE
    seuil = dec(request.form.get("seuil_alerte"))
    cost = dec(request.form.get("cost_avg"))
    prix_vente_base = dec(request.form.get("prix_vente_base"))
    unite_vente_id = request.form.get("unite_vente_id", type=int)
    facteur = dec(request.form.get("facteur"), default="1")
    prix_vente_unite = dec(request.form.get("prix_vente_unite"))
    devise_unite = request.form.get("devise_unite") or currency
    is_default = bool(request.form.get("is_sale_default"))

    errors = []
    if not name:
        errors.append("Le nom du produit est obligatoire.")
    if not base_unit_id:
        errors.append("L'unite de stock est obligatoire.")
    if unite_vente_id and unite_vente_id == base_unit_id:
        errors.append("L'unite de vente doit differer de l'unite de stock.")
    if unite_vente_id and facteur <= 0:
        errors.append("Le facteur de conversion doit etre positif.")

    is_new = product is None
    if is_new and not code:
        code = _next_product_code()
    if not code:
        errors.append("Le code produit est obligatoire.")

    existing = Product.query.filter_by(code=code).first()
    if existing and (product is None or existing.id != product.id):
        errors.append("Ce code produit existe deja.")

    if errors:
        for message in errors:
            flash(message, "danger")
        return redirect(request.url)

    if is_new:
        product = Product()
        db.session.add(product)

    product.code = code
    product.name = name
    product.base_unit_id = base_unit_id
    product.category_id = category_id or None
    product.currency = currency
    product.kind = kind
    product.seuil_alerte = seuil
    product.is_perishable = bool(request.form.get("is_perishable"))
    product.track_lot = bool(request.form.get("track_lot"))
    expiry_raw = request.form.get("default_expiry_date")
    product.default_expiry_date = None
    if expiry_raw:
        try:
            from datetime import datetime
            product.default_expiry_date = datetime.strptime(expiry_raw, "%Y-%m-%d").date()
        except ValueError:
            product.default_expiry_date = None
    shelf_raw = (request.form.get("shelf_life_days") or "").strip()
    product.shelf_life_days = int(shelf_raw) if shelf_raw.isdigit() and int(shelf_raw) > 0 else None
    product.active = bool(request.form.get("active"))
    product.notes = (request.form.get("notes") or "").strip() or None

    ancien_cost = product.cost_avg
    if is_new or cost != 0:
        product.cost_avg = cost

    db.session.flush()

    # Prix de vente de l'unite de base
    _set_base_price(product, prix_vente_base, currency)

    # Unite de vente secondaire
    if unite_vente_id:
        _set_selling_unit(
            product,
            unite_vente_id,
            facteur,
            prix_vente_unite,
            devise_unite,
            is_default,
        )
    log_action(
        "product_create" if is_new else "product_update",
        entity="product",
        entity_uuid=product.uuid,
        after={"code": code, "name": name, "base_unit_id": base_unit_id},
        commit=True,
    )
    flash(f"Produit « {product.name} » enregistré.", "success")
    return redirect(url_for("products.index"))


@products_bp.route("/<int:product_id>")
@login_required
@permission_required(P.PRODUCTS_VIEW)
def detail(product_id):
    product = db.session.get(Product, product_id) or abort(404)
    movements = product_movements(product)[:50]
    prices = (
        PriceHistory.query.filter_by(product_id=product.id)
        .order_by(PriceHistory.created_at.desc())
        .limit(20)
        .all()
    )
    used_unit_ids = {pu.unit_id for pu in product.selling_units}
    used_unit_ids.add(product.base_unit_id)
    available_units = [u for u in _units() if u.id not in used_unit_ids]
    pending_qty = dec(
        db.session.query(db.func.coalesce(db.func.sum(StockEntryRequest.qty_base), 0))
        .filter(
            StockEntryRequest.product_id == product.id,
            StockEntryRequest.status == StockEntryStatus.EN_ATTENTE,
        )
        .scalar()
    )
    return render_template(
        "products/detail.html",
        product=product,
        movements=movements,
        prices=prices,
        available_units=available_units,
        currencies=CURRENCIES,
        pending_qty=pending_qty,
    )


@products_bp.route("/<int:product_id>/unites", methods=["POST"])
@login_required
@permission_required(P.PRODUCTS_MANAGE)
def add_unit(product_id):
    product = db.session.get(Product, product_id) or abort(404)
    unit_id = request.form.get("unit_id", type=int)
    factor = dec(request.form.get("factor"), default="1")
    prix = dec(request.form.get("prix_vente"))
    currency = request.form.get("currency") or product.currency

    if not unit_id:
        flash("Selectionnez une unite.", "danger")
        return redirect(url_for("products.detail", product_id=product.id))
    if factor <= 0:
        flash("Le facteur de conversion doit etre positif.", "danger")
        return redirect(url_for("products.detail", product_id=product.id))
    if ProductUnit.query.filter_by(product_id=product.id, unit_id=unit_id).first():
        flash("Cette unite est deja associee au produit.", "danger")
        return redirect(url_for("products.detail", product_id=product.id))

    pu = ProductUnit(
        product_id=product.id,
        unit_id=unit_id,
        factor=factor,
        prix_vente=prix,
        currency=currency,
        is_sale_default=bool(request.form.get("is_sale_default")),
    )
    if pu.is_sale_default:
        ProductUnit.query.filter_by(product_id=product.id).update({"is_sale_default": False})
    db.session.add(pu)
    if prix > 0:
        db.session.add(
            PriceHistory(
                product_id=product.id,
                kind=PriceKind.VENTE,
                prix=prix,
                currency=currency,
            )
        )
    log_action(
        "product_unit_add",
        entity="product",
        entity_uuid=product.uuid,
        after={"unit_id": unit_id, "factor": str(factor), "prix": str(prix)},
        commit=True,
    )
    flash("Unite de vente ajoutee.", "success")
    return redirect(url_for("products.detail", product_id=product.id))


@products_bp.route("/<int:product_id>/unites/<int:pu_id>/supprimer", methods=["POST"])
@login_required
@permission_required(P.PRODUCTS_MANAGE)
def delete_unit(product_id, pu_id):
    product = db.session.get(Product, product_id) or abort(404)
    pu = db.session.get(ProductUnit, pu_id)
    if pu is None or pu.product_id != product.id:
        abort(404)
    db.session.delete(pu)
    log_action(
        "product_unit_remove",
        entity="product",
        entity_uuid=product.uuid,
        before={"unit_id": pu.unit_id, "factor": str(pu.factor)},
        commit=True,
    )
    flash("Unite de vente supprimee.", "success")
    return redirect(url_for("products.detail", product_id=product.id))


@products_bp.route("/categories", methods=["GET", "POST"])
@login_required
@permission_required(P.PRODUCTS_VIEW)
def categories():
    if request.method == "POST":
        if not request.form.get("csrf_token"):
            abort(400)
        name = (request.form.get("name") or "").strip()
        if not name:
            flash("Le nom de la categorie est obligatoire.", "danger")
        elif Category.query.filter_by(name=name).first():
            flash("Cette categorie existe deja.", "danger")
        else:
            category = Category(name=name, description=(request.form.get("description") or "").strip() or None)
            db.session.add(category)
            log_action("category_create", entity="category", after={"name": name}, commit=True)
            flash(f"Categorie « {name} » creee.", "success")
        return redirect(url_for("products.categories"))

    return render_template("products/categories.html", categories=_categories())


@products_bp.route("/unites")
@login_required
@permission_required(P.PRODUCTS_VIEW)
def units():
    return render_template("products/units.html", units=_units())
