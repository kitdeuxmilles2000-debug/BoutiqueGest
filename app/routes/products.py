"""Catalogue : produits, unites de vente, categories."""
from flask import Blueprint, abort, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required
from decimal import Decimal
from datetime import datetime, timedelta
from sqlalchemy import update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm.attributes import set_committed_value

from app.extensions import db
from app.models.catalog import (
    Category,
    PriceHistory,
    PriceKind,
    Product,
    PRODUCT_PRESET_BASE_UNITS,
    PRODUCT_PRESET_UNIT_KINDS,
    ProductKind,
    ProductStatus,
    PRODUCT_STATUS_BADGES,
    PRODUCT_STATUS_LABELS,
    ProductUnit,
    Unit,
    normalize_product_name,
)
from app.models.base import utcnow
from app.models.stock import Batch, MovementKind, StockEntryRequest, StockEntryStatus
from app.security.audit import log_action
from app.security.decorators import admin_password_required, permission_required
from app.services.pagination import paginate_list
from app.security.owner import is_admin_like, is_owner
from app.security.permissions import P
from app.services import pricing as pricing_service
from app.services.stock import dec, product_movements, record_movement
products_bp = Blueprint("products", __name__, url_prefix="/produits")

CURRENCIES = ("CDF", "USD")


def _units():
    from app.services.seed import ensure_catalog_defaults

    ensure_catalog_defaults()
    return Unit.query.filter(Unit.product_id.is_(None)).order_by(Unit.label).all()


def _categories():
    from app.services.seed import ensure_catalog_defaults

    ensure_catalog_defaults()
    return Category.query.order_by(Category.name).all()


@products_bp.route("/")
@login_required
@permission_required(P.PRODUCTS_VIEW)
def index():
    search = (request.args.get("q") or "").strip()
    category_id = request.args.get("category", type=int)
    alert = request.args.get("alert")
    statut = (request.args.get("statut") or "").strip()

    query = Product.query
    if search:
        like = f"%{search}%"
        query = query.filter(db.or_(Product.name.ilike(like), Product.code.ilike(like)))
    if category_id:
        query = query.filter(Product.category_id == category_id)

    products = query.order_by(Product.name).all()
    if alert == "low":
        products = [p for p in products if p.is_low_stock or p.is_out_of_stock]

    from app.models.stock import StockEntryRequest, StockEntryStatus

    pending_rows = (
        db.session.query(StockEntryRequest.product_id, db.func.sum(StockEntryRequest.qty_base))
        .filter(StockEntryRequest.status == StockEntryStatus.EN_ATTENTE)
        .group_by(StockEntryRequest.product_id)
        .all()
    )
    pending_qty = {pid: (qty or dec(0)) for pid, qty in pending_rows}
    if statut == "attente":
        validated_ids = {
            pid
            for (pid,) in db.session.query(StockEntryRequest.product_id)
            .filter(StockEntryRequest.status == StockEntryStatus.VALIDEE)
            .distinct()
            .all()
        }
        products = [
            p for p in products
            if p.id not in validated_ids and dec(p.stock_qty) <= 0
        ]

    pager = paginate_list(products)
    products = pager.items
    views = {}
    for p in products:
        pu = pricing_service.default_sale_unit(p)
        target = pricing_service.target_margin(p)
        if pu is not None:
            status_m = pricing_service.margin_status(
                pu.prix_vente, pricing_service.sale_unit_cost(p, pu), target
            )
        else:
            status_m = pricing_service.margin_status(0, 0, target)
        views[p.id] = {
            "stock_text": pricing_service.stock_in_sale_units(p, pu),
            "margin": status_m,
            "target": target,
        }

    familles = sorted({getattr(p, 'famille', None) for p in Product.query.all() if getattr(p, 'famille', None)})
    couleurs = sorted({getattr(p, 'couleur', None) for p in Product.query.all() if getattr(p, 'couleur', None)})

    return render_template(
        "products/index.html",
        products=products,
        pager=pager,
        views=views,
        categories=_categories(),
        category_id=category_id,
        search=search,
        alert=alert,
        statut=statut,
        pending_qty=pending_qty,
        familles=familles,
        couleurs=couleurs,
        product_status_labels=PRODUCT_STATUS_LABELS,
        product_status_badges=PRODUCT_STATUS_BADGES,
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
        preset=None,
        units_hors_base=[],
        custom_selling_units=[],
        batches=[],
        shared_sale_unit=None,
        default_margin=pricing_service.default_target_margin(),
        stock_manage_allowed=current_user.has_permission(P.STOCK_MANAGE),
    )


def _distinct_values(column):
    return sorted({v for (v,) in db.session.query(column).distinct().all() if v})


@products_bp.route("/<int:product_id>/modifier", methods=["GET", "POST"])
@login_required
@permission_required(P.PRODUCTS_MANAGE)
def edit(product_id):
    if product_id == 0:
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
            preset=None,
            units_hors_base=[],
            custom_selling_units=[],
            batches=[],
            shared_sale_unit=None,
            default_margin=pricing_service.default_target_margin(),
            stock_manage_allowed=current_user.has_permission(P.STOCK_MANAGE),
        )
    product = db.session.get(Product, product_id) or abort(404)
    if request.method == "POST":
        return _save_product(product)
    base_pu = ProductUnit.query.filter_by(
        product_id=product.id, unit_id=product.base_unit_id
    ).first()
    hors_base = [
        pu for pu in product.selling_units
        if pu.active and pu.unit_id != product.base_unit_id and pu.unit.product_id is None
    ]
    custom_selling_units = [
        pu for pu in product.selling_units
        if pu.active and pu.unit.product_id == product.id
    ]
    batches = (
        Batch.query.filter_by(product_id=product.id, active=True)
        .order_by(Batch.expiry_date.is_(None), Batch.expiry_date.asc())
        .all()
    )
    shared_sale_unit = next(
        (
            pu for pu in product.selling_units
            if pu.unit_id != product.base_unit_id and pu.unit.product_id is None
        ),
        None,
    )
    return render_template(
        "products/form.html",
        product=product,
        units=_units(),
        categories=_categories(),
        kinds=ProductKind,
        currencies=CURRENCIES,
        base_prix=base_pu.prix_vente if base_pu else None,
        preset=product.type_mesure,
        units_hors_base=hors_base,
        custom_selling_units=custom_selling_units,
        batches=batches,
        shared_sale_unit=shared_sale_unit,
        default_margin=pricing_service.default_target_margin(),
        stock_manage_allowed=current_user.has_permission(P.STOCK_MANAGE),
    )


def _next_product_code():
    from app.models.base import utcnow
    today = utcnow().strftime("%y%m%d")
    count = Product.query.count() + 1
    return f"PRD-{today}-{count:04d}"


def _claim_product_edit(product):
    raw_version = (request.form.get("form_version") or "").strip()
    try:
        submitted_version = datetime.fromisoformat(raw_version)
    except ValueError:
        submitted_version = None
    if submitted_version is None or submitted_version.tzinfo is not None:
        flash("La fiche a changé ou est trop ancienne. Rechargez-la avant d'enregistrer.", "warning")
        return False

    claimed_version = max(utcnow(), submitted_version + timedelta(microseconds=1))
    result = db.session.execute(
        update(Product)
        .where(Product.id == product.id, Product.updated_at == submitted_version)
        .values(updated_at=claimed_version)
    )
    if result.rowcount != 1:
        db.session.rollback()
        flash(
            "Cette fiche a été modifiée par un autre utilisateur. Vérifiez les valeurs actualisées avant de réessayer.",
            "warning",
        )
        return False

    set_committed_value(product, "updated_at", claimed_version)
    return True


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
    pu.active = True
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
    pu.active = True
    if is_default:
        ProductUnit.query.filter_by(product_id=product.id).update(
            {"is_sale_default": False}
        )
        pu.is_sale_default = True
    db.session.flush()
    return pu


def _move_base_unit_rows(product, ancienne_base, nouvelle_base):
    """Quand l'unite de stock change, deplace la ligne de prix de base au lieu
    de laisser une unite fantome au facteur 1 (qui fausserait les conversions)."""
    if ancienne_base == nouvelle_base:
        return  # rien a deplacer : evite de supprimer la ligne de base existante
    nouvelle_ligne = ProductUnit.query.filter_by(
        product_id=product.id, unit_id=nouvelle_base
    ).first()
    for row in ProductUnit.query.filter_by(
        product_id=product.id, unit_id=ancienne_base
    ).all():
        if abs(dec(row.factor) - Decimal("1")) > Decimal("0.000001"):
            continue  # ancienne unite avec une vraie conversion : on la conserve
        if nouvelle_ligne is None:
            row.unit_id = nouvelle_base
            nouvelle_ligne = row
        else:
            if row.is_sale_default:
                nouvelle_ligne.is_sale_default = True
            db.session.delete(row)
    db.session.flush()


def _save_product(product):
    from app.services.product_units import parse_sale_unit_rows, save_product_sale_units

    if product is not None and not _claim_product_edit(product):
        return redirect(request.url)

    code = (
        request.form.get("code")
        or (product.code if product else "")
    ).strip().upper()
    name = (
        request.form.get("name")
        if "name" in request.form
        else (product.name if product else "")
    ).strip()
    base_unit_id = request.form.get("base_unit_id", type=int) or (product.base_unit_id if product else None)
    category_id = request.form.get("category_id", type=int) or (product.category_id if product else None)
    currency = request.form.get("currency") or (product.currency if product else "CDF")
    kind = request.form.get("kind") or (product.kind if product else ProductKind.AUTRE)
    seuil = dec(
        request.form.get("seuil_alerte")
        if "seuil_alerte" in request.form
        else (product.seuil_alerte if product else None)
    )
    cost = dec(
        request.form.get("cost_avg")
        if "cost_avg" in request.form
        else (product.cost_avg if product else None)
    )
    stock_counted = None
    stock_reason = (request.form.get("stock_reason") or "").strip()
    stock_counted_raw = (request.form.get("stock_counted") or "").strip().replace(",", ".")
    if stock_counted_raw:
        try:
            stock_counted = Decimal(stock_counted_raw)
        except ArithmeticError:
            stock_counted = None
    prix_vente_base = dec(request.form.get("prix_vente_base"))
    unite_vente_id = request.form.get("unite_vente_id", type=int)
    product_preset = (request.form.get("product_preset") or "").strip()
    type_mesure = (
        (request.form.get("type_mesure") or "").strip()
        or product_preset
        or (product.type_mesure if product else "autre")
    )
    technical_attributes = {
        attribute: (
            (request.form.get(attribute) or "").strip() or None
            if attribute in request.form
            else getattr(product, attribute, None)
        )
        for attribute in ("famille", "couleur", "marque", "modele")
    }
    facteur = dec(request.form.get("facteur"), default="1")
    initial_quantity = dec(request.form.get("initial_quantity"))
    initial_unit_factor = dec(request.form.get("initial_unit_factor"), default="1")
    prix_vente_unite = dec(request.form.get("prix_vente_unite"))
    devise_unite = request.form.get("devise_unite") or currency
    is_default = "1" in request.form.getlist("is_sale_default") or (
        "on" in request.form.getlist("is_sale_default")
    )
    is_new = product is None
    active = (
        any(value in ("1", "on", "true") for value in request.form.getlist("active"))
        if "active" in request.form
        else (product.active if product else True)
    )
    is_perishable = (
        any(value in ("1", "on", "true") for value in request.form.getlist("is_perishable"))
        if "is_perishable" in request.form
        else (product.is_perishable if product else False)
    )
    track_lot = (
        any(value in ("1", "on", "true") for value in request.form.getlist("track_lot"))
        if "track_lot" in request.form
        else (product.track_lot if product else False)
    )
    default_expiry_date = product.default_expiry_date if product else None
    expiry_raw = request.form.get("default_expiry_date")
    if "default_expiry_date" in request.form:
        try:
            default_expiry_date = (
                datetime.strptime(expiry_raw, "%Y-%m-%d").date()
                if expiry_raw
                else None
            )
        except ValueError:
            default_expiry_date = None
    shelf_life_days = product.shelf_life_days if product else None
    if "shelf_life_days" in request.form:
        shelf_life_raw = (request.form.get("shelf_life_days") or "").strip()
        try:
            shelf_life_days = int(shelf_life_raw) if shelf_life_raw else None
            if shelf_life_days is not None and shelf_life_days < 0:
                raise ValueError
        except ValueError:
            shelf_life_days = None
    base_unit = db.session.get(Unit, base_unit_id) if base_unit_id else None
    try:
        custom_sale_units = parse_sale_unit_rows(
            request.form, "sale_unit", product_preset, base_unit
        )
    except ValueError as exc:
        flash(str(exc), "danger")
        return redirect(request.url)

    sale_unit = db.session.get(Unit, unite_vente_id) if unite_vente_id else None
    errors = []
    marge_raw = (request.form.get("marge_cible") or "").strip().replace(",", ".")
    marge_cible = product.marge_cible if product and "marge_cible" not in request.form else None
    if marge_raw:
        try:
            marge_cible = Decimal(marge_raw)
        except ArithmeticError:
            marge_cible = None
        if marge_cible is None or not (0 <= marge_cible < 100):
            errors.append("La marge cible doit être un nombre entre 0 et 99 %.")
    if not name:
        errors.append("Le nom du produit est obligatoire.")
    if "default_expiry_date" in request.form and expiry_raw:
        try:
            datetime.strptime(expiry_raw, "%Y-%m-%d")
        except ValueError:
            errors.append("La date d'expiration par défaut n'est pas valide.")
    if "shelf_life_days" in request.form:
        shelf_life_raw = (request.form.get("shelf_life_days") or "").strip()
        if shelf_life_raw:
            try:
                if int(shelf_life_raw) < 0:
                    raise ValueError
            except ValueError:
                errors.append("La durée de conservation doit être un nombre positif ou nul.")
    if len(type_mesure) > 30:
        errors.append("Le type de mesure ne peut pas dépasser 30 caractères.")
    for attribute, value in technical_attributes.items():
        if value and len(value) > 80:
            errors.append(f"{attribute.capitalize()} ne peut pas dépasser 80 caractères.")
    if not base_unit_id:
        errors.append("L'unite de stock est obligatoire.")
    elif base_unit is None or base_unit.product_id is not None:
        errors.append("L'unite de stock selectionnee n'existe pas.")
    elif product_preset and (
        product_preset not in PRODUCT_PRESET_UNIT_KINDS
        or base_unit.kind
        not in PRODUCT_PRESET_UNIT_KINDS[product_preset]
    ):
        errors.append("L'unite de stock ne correspond pas au type de produit selectionne.")
    elif is_new and not product_preset:
        errors.append("Le type de produit est obligatoire.")
    elif (
        is_new
        and base_unit is not None
        and PRODUCT_PRESET_BASE_UNITS.get(product_preset)
        and base_unit.code != PRODUCT_PRESET_BASE_UNITS[product_preset]
    ):
        errors.append("Choisissez la plus petite unité comme unité de comptage du stock.")
    if not category_id:
        errors.append("La categorie du produit est obligatoire.")
    elif db.session.get(Category, category_id) is None:
        errors.append("La categorie selectionnee n'existe pas.")
    if unite_vente_id and (
        sale_unit is None or sale_unit.product_id is not None
    ):
        errors.append("L'unite de vente selectionnee n'existe pas.")
    elif unite_vente_id and product_preset in PRODUCT_PRESET_UNIT_KINDS and (
        sale_unit.kind
        not in PRODUCT_PRESET_UNIT_KINDS[product_preset]
    ):
        errors.append("L'unite de vente ne correspond pas au type de produit selectionne.")
    if unite_vente_id and unite_vente_id == base_unit_id:
        errors.append("L'unite de vente doit differer de l'unite de stock.")
    if unite_vente_id and facteur <= 0:
        errors.append("Le facteur de conversion doit etre positif.")
    if is_default and any(row["is_default"] for row in custom_sale_units):
        errors.append("Selectionnez une seule unite de vente par defaut.")

    if is_new and not code:
        code = _next_product_code()
    if not code:
        errors.append("Le code produit est obligatoire.")
    if stock_counted_raw:
        if product is None:
            errors.append("La quantité de stock ne peut être corrigée qu'après la création du produit.")
        if not is_owner(current_user):
            errors.append("Seul le propriétaire peut corriger directement la quantité en stock.")
        if stock_counted is None or not stock_counted.is_finite() or stock_counted < 0:
            errors.append("La quantité réelle en stock doit être un nombre positif ou nul.")
        if not stock_reason:
            errors.append("Indiquez le motif de la correction de stock.")

    existing = Product.query.filter_by(code=code).first()
    if existing and (product is None or existing.id != product.id):
        errors.append("Ce code produit existe deja.")
    if name:
        duplicate_query = Product.query.filter(
            Product.normalized_name == normalize_product_name(name)
        )
        duplicate_query = (
            duplicate_query.filter_by(category_id=category_id)
            if category_id
            else duplicate_query.filter(Product.category_id.is_(None))
        )
        if product is not None:
            duplicate_query = duplicate_query.filter(Product.id != product.id)
        legacy_same_name = (
            product is not None
            and normalize_product_name(product.name) == normalize_product_name(name)
            and product.normalized_name != normalize_product_name(name)
        )
        if not legacy_same_name and duplicate_query.first():
            errors.append("Un produit portant ce nom existe déjà dans cette catégorie.")
    if is_new and initial_quantity < 0:
        errors.append("La quantité initiale ne peut pas être négative.")
    if is_new and initial_quantity > 0:
        configured_factors = {Decimal("1")} | {row["factor"] for row in custom_sale_units}
        if initial_unit_factor not in configured_factors:
            errors.append("Choisissez une unité de réception configurée pour ce produit.")
        if not current_user.has_permission(P.STOCK_MANAGE):
            errors.append("La permission de gestion du stock est requise pour saisir une quantité initiale.")

    if errors:
        for message in errors:
            flash(message, "danger")
        return redirect(request.url)

    if is_new:
        product = Product()
        db.session.add(product)
    else:
        _move_base_unit_rows(product, product.base_unit_id, base_unit_id)

    product.code = code
    legacy_name_key = product.normalized_name
    preserve_legacy_duplicate_key = (
        not is_new
        and normalize_product_name(product.name) == normalize_product_name(name)
        and legacy_name_key != normalize_product_name(name)
    )
    product.name = name
    if preserve_legacy_duplicate_key:
        product.normalized_name = legacy_name_key
    product.base_unit_id = base_unit_id
    product.category_id = category_id or None
    product.currency = currency
    product.kind = kind
    product.type_mesure = type_mesure
    for attribute, value in technical_attributes.items():
        setattr(product, attribute, value)
    product.seuil_alerte = seuil
    product.active = active
    product.marge_cible = marge_cible
    product.is_perishable = is_perishable
    product.track_lot = track_lot
    product.default_expiry_date = default_expiry_date
    product.shelf_life_days = shelf_life_days

    ancien_cost = product.cost_avg
    if is_new or cost != 0:
        product.cost_avg = cost

    if is_new:
        if current_user.has_permission(P.PRODUCTS_MANAGE):
            product.validation_status = ProductStatus.VALIDE
            product.active = True
            product.validated_by_id = current_user.id
            product.validated_at = utcnow()
        else:
            product.validation_status = ProductStatus.EN_ATTENTE
            product.active = False
            product.proposed_by_id = current_user.id

    try:
        db.session.flush()
    except IntegrityError:
        db.session.rollback()
        flash("Le code ou le nom du produit existe déjà dans cette catégorie.", "danger")
        return redirect(request.url)

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
    try:
        save_product_sale_units(product, custom_sale_units, currency)
    except ValueError as exc:
        db.session.rollback()
        flash(str(exc), "danger")
        return redirect(request.url)
    if stock_counted is not None:
        stock_delta = stock_counted - dec(product.stock_qty)
        if stock_delta:
            previous_stock = dec(product.stock_qty)
            record_movement(
                product,
                MovementKind.CORRECTION_INVENTAIRE,
                stock_delta,
                source_type="product_edit",
                reason=stock_reason,
                user_id=current_user.id,
                commit=False,
            )
            log_action(
                "stock_correction_product_edit",
                entity="product",
                entity_uuid=product.uuid,
                before={"stock_qty": str(previous_stock)},
                after={"stock_qty": str(stock_counted), "delta": str(stock_delta)},
                reason=stock_reason,
                commit=False,
            )
    if is_new and initial_quantity > 0:
        from app.services.stock_validation import create_entry_request

        try:
            initial_request = create_entry_request(
                product=product,
                quantity=initial_quantity * initial_unit_factor,
                unit_id=base_unit_id,
                cost_unit=cost,
                currency=currency,
                reason="Stock initial à la création du produit",
                notes="Approvisionnement initial saisi sur la fiche produit.",
                user_id=current_user.id,
                commit=False,
            )
        except ValueError as exc:
            db.session.rollback()
            flash(str(exc), "danger")
            return redirect(request.url)
        log_action(
            "stock_entry_initial_product",
            entity="stock_entry_request",
            entity_uuid=initial_request.uuid,
            after={
                "product_id": product.id,
                "qty_base": str(initial_request.qty_base),
                "status": initial_request.status,
            },
            commit=False,
        )
    try:
        log_action(
            "product_create" if is_new else "product_update",
            entity="product",
            entity_uuid=product.uuid,
            after={"code": code, "name": name, "base_unit_id": base_unit_id, "validation_status": product.validation_status},
            commit=True,
        )
    except IntegrityError:
        db.session.rollback()
        flash("Un produit avec ce code ou ce nom existe déjà. Vérifiez la catégorie avant de réessayer.", "danger")
        return redirect(request.url)
    if is_new and product.validation_status == ProductStatus.EN_ATTENTE:
        flash(f"Produit « {product.name} » proposé. En attente de validation par un administrateur.", "warning")
    else:
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


@products_bp.route("/<int:product_id>/supprimer", methods=["GET", "POST"])
@login_required
@permission_required(P.PRODUCTS_MANAGE)
@admin_password_required()
def delete(product_id):
    from app.services.notifications import sync_alerts
    from app.services.product_deletion import collect_impact, delete_product

    product = db.session.get(Product, product_id) or abort(404)
    impact = collect_impact(product)
    if request.method == "POST":
        reason = (request.form.get("reason") or "").strip() or None
        snapshot = {
            "id": product.id,
            "code": product.code,
            "name": product.name,
            "stock_qty": str(product.stock_qty or 0),
        }
        product_uuid = product.uuid
        product_name = product.name
        summary = delete_product(product, commit=False)
        log_action(
            "product_delete",
            entity="product",
            entity_uuid=product_uuid,
            before=snapshot,
            after={
                "sales_cancelled": summary["sales"],
                "cash_movements_removed": summary["cash_movements"],
                "credits_removed": summary["credits"],
                "stock_movements_removed": summary["movements"],
                "pending_entries_removed": summary["pending_entries"],
            },
            reason=reason,
            commit=False,
        )
        sync_alerts(commit=False)
        db.session.commit()
        flash(
            f"Produit « {product_name} » supprimé définitivement. "
            f"{summary['sales']} vente(s) et {summary['cash_movements']} mouvement(s) de caisse annulés.",
            "success",
        )
        return redirect(url_for("products.index"))

    return render_template(
        "products/delete.html",
        product=product,
        impact=impact,
        needs_password=True,
    )


@products_bp.route("/<int:product_id>/unites", methods=["POST"])
@login_required
@permission_required(P.PRODUCTS_MANAGE)
def add_unit(product_id):
    product = db.session.get(Product, product_id) or abort(404)
    unit_id = request.form.get("unit_id", type=int)
    unit = db.session.get(Unit, unit_id) if unit_id else None
    factor = dec(request.form.get("factor"), default="1")
    prix = dec(request.form.get("prix_vente"))
    currency = request.form.get("currency") or product.currency

    if unit is None or unit.product_id is not None:
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
@admin_password_required()
def delete_unit(product_id, pu_id):
    product = db.session.get(Product, product_id) or abort(404)
    pu = db.session.get(ProductUnit, pu_id)
    if pu is None or pu.product_id != product.id:
        abort(404)
    if pu.unit.product_id == product.id:
        pu.active = False
        pu.is_sale_default = False
    else:
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


@products_bp.route("/categories/<int:category_id>/supprimer", methods=["POST"])
@login_required
@permission_required(P.PRODUCTS_MANAGE)
@admin_password_required()
def delete_category(category_id):
    category = db.session.get(Category, category_id) or abort(404)
    used = Product.query.filter_by(category_id=category.id).count()
    if used:
        flash(f"Catégorie « {category.name} » utilisée par {used} produit(s) : suppression refusée.", "danger")
        return redirect(url_for("products.categories"))
    name = category.name
    db.session.delete(category)
    log_action("category_delete", entity="category", after={"name": name}, commit=True)
    flash(f"Catégorie « {name} » supprimée.", "success")
    return redirect(url_for("products.categories"))


@products_bp.route("/unites")
@login_required
@permission_required(P.PRODUCTS_VIEW)
def units():
    return render_template("products/units.html", units=_units())


@products_bp.route("/unites/<int:unit_id>/supprimer", methods=["POST"])
@login_required
@permission_required(P.PRODUCTS_MANAGE)
@admin_password_required()
def delete_global_unit(unit_id):
    unit = db.session.get(Unit, unit_id) or abort(404)
    if unit.is_system:
        flash(f"L'unité système « {unit.label} » ne peut pas être supprimée.", "danger")
        return redirect(url_for("products.units"))
    used = (
        Product.query.filter_by(base_unit_id=unit.id).count()
        + ProductUnit.query.filter_by(unit_id=unit.id).count()
    )
    if used:
        flash(f"Unité « {unit.label} » utilisée par {used} élément(s) : suppression refusée.", "danger")
        return redirect(url_for("products.units"))
    label = unit.label
    db.session.delete(unit)
    log_action("unit_delete", entity="unit", after={"label": label}, commit=True)
    flash(f"Unité « {label} » supprimée.", "success")
    return redirect(url_for("products.units"))


@products_bp.route("/proposer", methods=["GET", "POST"])
@login_required
@permission_required(P.PRODUCTS_VIEW)
def proposer():
    if request.method == "POST":
        code = (request.form.get("code") or "").strip().upper()
        name = (request.form.get("name") or "").strip()
        base_unit_id = request.form.get("base_unit_id", type=int)
        category_id = request.form.get("category_id", type=int)
        currency = request.form.get("currency") or "CDF"
        kind = request.form.get("kind") or ProductKind.AUTRE
        seuil = dec(request.form.get("seuil_alerte"))

        errors = []
        if not name:
            errors.append("Le nom du produit est obligatoire.")
        if not base_unit_id:
            errors.append("L'unité de stock est obligatoire.")
        elif (
            db.session.get(Unit, base_unit_id) is None
            or db.session.get(Unit, base_unit_id).product_id is not None
        ):
            errors.append("L'unité de stock sélectionnée n'est pas valide.")
        if category_id and db.session.get(Category, category_id) is None:
            errors.append("La catégorie sélectionnée n'existe pas.")
        if not code:
            code = _next_product_code()
        existing = Product.query.filter_by(code=code).first()
        if existing:
            errors.append("Ce code produit existe déjà.")
        proposal_duplicate_query = Product.query.filter(
            Product.normalized_name == normalize_product_name(name)
        )
        proposal_duplicate_query = (
            proposal_duplicate_query.filter_by(category_id=category_id)
            if category_id
            else proposal_duplicate_query.filter(Product.category_id.is_(None))
        )
        if name and proposal_duplicate_query.first():
            errors.append("Un produit portant ce nom existe déjà dans cette catégorie.")

        if errors:
            for message in errors:
                flash(message, "danger")
            return render_template(
                "products/proposer.html",
                units=_units(),
                categories=_categories(),
                kinds=ProductKind,
                currencies=CURRENCIES,
            )

        product = Product()
        product.code = code
        product.name = name
        product.base_unit_id = base_unit_id
        product.category_id = category_id or None
        product.currency = currency
        product.kind = kind
        product.seuil_alerte = seuil
        product.active = False
        product.validation_status = ProductStatus.EN_ATTENTE
        product.proposed_by_id = current_user.id
        db.session.add(product)
        try:
            db.session.flush()
        except IntegrityError:
            db.session.rollback()
            flash("Le code ou le nom du produit existe déjà dans cette catégorie.", "danger")
            return redirect(request.url)

        log_action(
            "product_propose",
            entity="product",
            entity_uuid=product.uuid,
            after={"code": code, "name": name},
            commit=True,
        )
        flash("Produit proposé. En attente de validation par un administrateur.", "warning")
        return redirect(url_for("products.index"))

    return render_template(
        "products/proposer.html",
        units=_units(),
        categories=_categories(),
        kinds=ProductKind,
        currencies=CURRENCIES,
    )


@products_bp.route("/<int:product_id>/valider", methods=["POST"])
@login_required
@permission_required(P.PRODUCTS_MANAGE)
def valider_proposition(product_id):
    product = db.session.get(Product, product_id) or abort(404)
    if product.validation_status != ProductStatus.EN_ATTENTE:
        flash("Ce produit n'est pas en attente de validation.", "warning")
        return redirect(url_for("products.index"))
    product.validation_status = ProductStatus.VALIDE
    product.active = True
    product.validated_by_id = current_user.id
    product.validated_at = utcnow()
    product.validation_note = (request.form.get("note") or "").strip() or None
    log_action("product_validate", entity="product", entity_uuid=product.uuid, commit=True)
    flash(f"Produit « {product.name} » validé.", "success")
    return redirect(url_for("products.index"))


@products_bp.route("/<int:product_id>/rejeter", methods=["POST"])
@login_required
@permission_required(P.PRODUCTS_MANAGE)
def rejeter_proposition(product_id):
    product = db.session.get(Product, product_id) or abort(404)
    if product.validation_status != ProductStatus.EN_ATTENTE:
        flash("Ce produit n'est pas en attente de validation.", "warning")
        return redirect(url_for("products.index"))
    product.validation_status = ProductStatus.REJETE
    product.active = False
    product.validated_by_id = current_user.id
    product.validated_at = utcnow()
    product.validation_note = (request.form.get("note") or "").strip() or None
    log_action("product_reject", entity="product", entity_uuid=product.uuid, reason=product.validation_note, commit=True)
    flash(f"Produit « {product.name} » rejeté.", "warning")
    return redirect(url_for("products.index"))
