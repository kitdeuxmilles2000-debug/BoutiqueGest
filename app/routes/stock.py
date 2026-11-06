"""Stock : vue d'ensemble, mouvements, entrees, pertes, inventaires et validations."""
from datetime import date

from flask import Blueprint, abort, flash, jsonify, redirect, render_template, request, url_for
from flask_login import current_user, login_required
from sqlalchemy.exc import IntegrityError

from app.extensions import db
from app.models.catalog import Product, ProductStatus, ProductUnit, normalize_product_name
from app.models.base import utcnow
from app.models.partners import Supplier
from app.models.stock import (
    InventoryLine,
    InventorySession,
    InventoryStatus,
    MOVEMENT_LABELS,
    MovementKind,
    STOCK_ENTRY_STATUS_BADGES,
    STOCK_ENTRY_STATUS_LABELS,
    StockEntryRequest,
    StockEntryStatus,
    StockMovement,
)
from app.security.audit import log_action
from app.security.decorators import admin_password_required, owner_only, owner_reauth_required, permission_required
from app.security.owner import find_admin_by_password
from app.security.permissions import P
from app.services.pagination import paginate, paginate_list
from app.services import pricing as pricing_service
from app.services import settings as settings_service
from app.services import stock as stock_service
from app.services import stock_validation as stock_validation_service
from app.services.stock import dec

stock_bp = Blueprint("stock", __name__, url_prefix="/stock")


def _active_products():
    return Product.query.filter_by(active=True).order_by(Product.name).all()


@stock_bp.route("/")
@login_required
@permission_required(P.STOCK_VIEW)
def index():
    products = _active_products()
    alerts = stock_service.stock_alerts(products)
    stock_totals, product_margins = stock_service.stock_financial_summary(products)
    rate_obj = settings_service.latest_rate()
    rate = dec(rate_obj.rate) if rate_obj else None
    # Totaux convertis pour affichage USD/CDF (valeur de stock au coût moyen)
    converted = {"CDF": dec("0"), "USD": dec("0")} if rate and rate > 0 else {}
    for cur, totals in stock_totals.items():
        val = dec(totals.get("stock_value"))
        if cur == "CDF":
            if converted:
                converted["CDF"] += val
                converted["USD"] += (val / rate).quantize(dec("0.01"))
        elif cur == "USD":
            if converted:
                converted["USD"] += val
                converted["CDF"] += (val * rate).quantize(dec("0.01"))
        elif converted:
            # devise non convertible: on ne l'ajoute pas aux totaux CDF/USD
            pass
    pager = paginate_list(products)
    return render_template(
        "stock/index.html",
        products=pager.items,
        pager=pager,
        alerts=alerts,
        stock_totals=stock_totals,
        converted_stock_totals=converted,
        rate=rate_obj,
        product_margins=product_margins,
        product_count=len(products),
    )


@stock_bp.route("/valorisation")
@login_required
@permission_required(P.STOCK_VIEW)
def valuation():
    products = _active_products()
    rate = settings_service.latest_rate()
    rows, native_totals, converted_totals = stock_service.stock_valuation_report(
        products, rate.rate if rate else None
    )
    pager = paginate_list(rows)
    return render_template(
        "stock/valuation.html",
        rows=pager.items,
        pager=pager,
        native_totals=native_totals,
        converted_totals=converted_totals,
        unconverted_currencies=sorted(set(native_totals) - {"CDF", "USD"}),
        rate=rate,
    )


@stock_bp.route("/ravitailler/<int:product_id>", methods=["POST"])
@login_required
@permission_required(P.STOCK_MANAGE)
@owner_reauth_required()
@owner_only()
def restock(product_id):
    product = db.session.get(Product, product_id) or abort(404)
    quantity_raw = (request.form.get("quantity") or "").strip()
    cost_unit = dec(request.form.get("cost_unit")) if request.form.get("cost_unit") else dec(product.cost_avg)
    unit_id = request.form.get("unit_id", type=int) or product.base_unit_id
    reason = (request.form.get("reason") or "Ravitaillement").strip() or "Ravitaillement"
    try:
        if not quantity_raw or quantity_raw == "0":
            raise ValueError("Indiquez une quantité positive.")
        quantity = dec(quantity_raw)
        if quantity <= 0:
            raise ValueError("Indiquez une quantité positive.")
        duplicate = stock_validation_service.find_duplicate_entry(
            product, quantity, unit_id, cost_unit,
            request.form.get("lot_number"),
        )
        req = stock_validation_service.create_entry_request(
            product=product,
            quantity=quantity,
            unit_id=unit_id,
            cost_unit=cost_unit,
            currency=product.currency,
            reason=reason,
            user_id=current_user.id,
            duplicate_approved_by_id=current_user.id if duplicate else None,
            commit=False,
        )
        if duplicate:
            log_action(
                "stock_duplicate_approved",
                entity="stock_entry_request",
                entity_uuid=req.uuid,
                after={"duplicate_of": duplicate.reference, "product_id": product.id},
                reason="Ravitaillement direct confirmé par un propriétaire.",
                approver_id=current_user.id,
                commit=False,
            )
        db.session.flush()
        req, _ = stock_validation_service.validate_entry_request(
            req, current_user.id, notes="Ravitaillement direct", commit=False
        )
        log_action(
            "stock_restock",
            entity="stock_entry_request",
            entity_uuid=req.uuid,
            after={"product_id": product.id, "qty_base": str(req.qty_base), "status": req.status},
            reason=reason,
            commit=False,
        )
        db.session.commit()
        flash(f"Ravitaillement effectué pour {product.name} : {quantity} ajouté.", "success")
    except ValueError as exc:
        db.session.rollback()
        flash(str(exc), "danger")
    except Exception as exc:
        db.session.rollback()
        flash(str(exc), "danger")
    return redirect(request.referrer or url_for("stock.index"))


@stock_bp.route("/mouvements")
@login_required
@permission_required(P.STOCK_VIEW)
def movements():
    product_id = request.args.get("product", type=int)
    kind = request.args.get("kind")
    query = StockMovement.query
    if product_id:
        query = query.filter_by(product_id=product_id)
    if kind:
        query = query.filter_by(kind=kind)
    pager = paginate(query.order_by(StockMovement.created_at.desc()))
    return render_template(
        "stock/movements.html",
        pager=pager,
        movements=pager.items,
        products=_active_products(),
        labels=MOVEMENT_LABELS,
        product_id=product_id,
        kind=kind,
    )


@stock_bp.route("/entree", methods=["GET", "POST"])
@login_required
@permission_required(P.STOCK_MANAGE)
def entry():
    # Tous les produits sont proposes (actifs et inactifs) avec badge d'etat.
    products = Product.query.order_by(Product.name).all()
    # Quantites en attente de validation par produit (base)
    pending_rows = (
        db.session.query(StockEntryRequest.product_id, db.func.coalesce(db.func.sum(StockEntryRequest.qty_base), 0))
        .filter(StockEntryRequest.status == StockEntryStatus.EN_ATTENTE)
        .group_by(StockEntryRequest.product_id)
        .all()
    )
    pending_qty = {pid: dec(qty) for pid, qty in pending_rows}

    if request.method == "POST":
        direct = request.form.get("direct_validate") == "1"
        approver = find_admin_by_password(request.form.get("owner_password")) if direct else None
        if direct and approver is None:
            flash("Mot de passe propriétaire/administrateur invalide : entrée non enregistrée.", "danger")
            return redirect(url_for("stock.entry"))

        product_id_raw = request.form.get("product_id", type=int)
        product = db.session.get(Product, product_id_raw) if product_id_raw else None
        unit_id = request.form.get("unit_id", type=int) or None
        if product and unit_id is None:
            unit_id = product.base_unit_id
        cost_unit = dec(request.form.get("cost")) if request.form.get("cost") else dec(product.cost_avg if product else 0)
        reason = (request.form.get("reason") or "").strip() or "Demande d'entrée"
        lot_number = (request.form.get("lot_number") or "").strip() or None
        if request.form.get("allow_mod"):
            lot_number = (request.form.get("m_lot_number") or lot_number or "").strip() or None
        expiry_raw = request.form.get("expiry_date") or ""
        if request.form.get("allow_mod") and request.form.get("m_expiry_date"):
            expiry_raw = request.form.get("m_expiry_date")
        expiry_date = None
        if expiry_raw:
            try:
                from datetime import datetime
                expiry_date = datetime.strptime(expiry_raw, "%Y-%m-%d").date()
            except ValueError:
                expiry_date = None
        if request.form.get("allow_mod") and request.form.get("m_cost"):
            cost_unit = dec(request.form.get("m_cost"))
        if request.form.get("allow_mod") and request.form.get("m_reason"):
            reason = (request.form.get("m_reason") or reason).strip() or reason
        supplier_id = request.form.get("supplier_id", type=int) or None

        # Creation directe d'un produit
        new_product = False
        if product is None and (request.form.get("new_product_name") or "").strip():
            try:
                product, sale_rows = _quick_create_product(current_user)
            except ValueError as exc:
                db.session.rollback()
                flash(str(exc), "danger")
                return redirect(url_for("stock.entry"))
            if product is None:
                flash("Création impossible : vérifiez le nom, le type, la catégorie et l'unité de stock.", "danger")
                return redirect(url_for("stock.entry"))
            new_product = True
            quantity = dec((request.form.get("new_qty_initial") or "0").strip())
            if quantity <= 0:
                db.session.rollback()
                flash("La quantité reçue du nouveau produit doit être positive.", "danger")
                return redirect(url_for("stock.entry"))
            received_unit = (request.form.get("new_qty_unit") or "base").strip()
            if received_unit == "base":
                unit_id = product.base_unit_id
            elif received_unit.startswith("sale:"):
                try:
                    form_index = int(received_unit.split(":", 1)[1])
                except ValueError:
                    db.session.rollback()
                    flash("Unité de réception invalide.", "danger")
                    return redirect(url_for("stock.entry"))
                sale_row = next(
                    (row for row in sale_rows if row["form_index"] == form_index),
                    None,
                )
                if sale_row is None or sale_row.get("unit_id") is None:
                    db.session.rollback()
                    flash("Sélectionnez un format de vente configuré pour la réception.", "danger")
                    return redirect(url_for("stock.entry"))
                unit_id = sale_row["unit_id"]
            else:
                db.session.rollback()
                flash("Unité de réception invalide.", "danger")
                return redirect(url_for("stock.entry"))
            cost_unit = dec(request.form.get("cost"))

        if product is None:
            flash("Produit introuvable.", "danger")
            return redirect(url_for("stock.entry"))
        if not new_product:
            quantity_raw = (request.form.get("quantity") or "").strip()
            if not quantity_raw or quantity_raw == "0":
                flash("Indiquez la quantité reçue pour le produit existant.", "danger")
                return redirect(url_for("stock.entry"))
            quantity = dec(quantity_raw)

        # Peremption : valeur du formulaire, sinon fiche produit, sinon duree de conservation
        if expiry_date is None and product.is_perishable:
            expiry_date = product.default_expiry_date
            if expiry_date is None and product.shelf_life_days:
                from datetime import timedelta
                expiry_date = utcnow().date() + timedelta(days=int(product.shelf_life_days))

        try:
            duplicate = stock_validation_service.find_duplicate_entry(
                product, quantity, unit_id, cost_unit, lot_number
            )
        except ValueError as exc:
            db.session.rollback()
            flash(str(exc), "danger")
            return redirect(url_for("stock.entry"))
        if duplicate and not direct:
            db.session.rollback()
            flash(
                f"Une entrée identique existe déjà aujourd'hui ({duplicate.reference}). "
                "Vérifiez qu'il s'agit bien d'un nouvel approvisionnement, puis utilisez "
                "« Entrer en stock directement » et confirmez avec le mot de passe administrateur.",
                "warning",
            )
            return redirect(url_for("stock.entry"))

        try:
            req = stock_validation_service.create_entry_request(
                product=product,
                quantity=quantity,
                unit_id=unit_id,
                cost_unit=cost_unit,
                currency=product.currency,
                reason=reason,
                lot_number=lot_number,
                expiry_date=expiry_date,
                supplier_id=supplier_id,
                user_id=current_user.id,
                duplicate_approved_by_id=approver.id if duplicate and approver else None,
                commit=False,
            )
            log_action(
                "stock_entry_request",
                entity="stock_entry_request",
                entity_uuid=req.uuid,
                after={"product_id": product.id, "qty_base": str(req.qty_base), "status": req.status},
                reason=reason,
                commit=False,
            )
            if duplicate and approver:
                log_action(
                    "stock_duplicate_approved",
                    entity="stock_entry_request",
                    entity_uuid=req.uuid,
                    after={
                        "duplicate_of": duplicate.reference,
                        "product_id": product.id,
                        "qty_base": str(req.qty_base),
                    },
                    reason="Nouvel approvisionnement confirmé malgré une entrée identique.",
                    approver_id=approver.id,
                    commit=False,
                )
            if direct:
                db.session.flush()
                req, _ = stock_validation_service.validate_entry_request(
                    req,
                    approver.id if duplicate and approver else current_user.id,
                    notes="Approvisionnement identique confirmé par mot de passe administrateur"
                    if duplicate
                    else "Entrée directe confirmée par mot de passe",
                    commit=False,
                )
                log_action(
                    "stock_entry_direct",
                    entity="stock_entry_request",
                    entity_uuid=req.uuid,
                    after={"product_id": product.id, "qty_base": str(req.qty_base), "status": req.status},
                    reason=reason,
                    commit=False,
                )
            db.session.commit()
            if direct:
                flash(
                    f"Entrée {req.reference} enregistrée : le stock et le coût moyen sont à jour.",
                    "success",
                )
                return redirect(url_for("stock.index"))
            flash(
                f"Demande d'entrée {req.reference} soumise. En attente de validation par le propriétaire.",
                "success",
            )
        except ValueError as exc:
            db.session.rollback()
            flash(str(exc), "danger")
            return redirect(url_for("stock.entry"))
        except IntegrityError:
            db.session.rollback()
            flash(
                "La base a détecté un conflit sur cette saisie. Vérifiez les entrées récentes avant de réessayer.",
                "warning",
            )
            return redirect(url_for("stock.entry"))

        return redirect(url_for("stock.entry_pending"))

    return render_template(
        "stock/entry.html",
        products=products,
        pending_qty=pending_qty,
        suppliers=Supplier.query.order_by(Supplier.name).all(),
        units=_stock_units(),
        categories=_stock_categories(),
        types_mesure=pricing_service.TYPES_MESURE,
        can_create=current_user.has_permission(P.PRODUCTS_MANAGE),
    )


@stock_bp.route("/entree/verifier-doublon", methods=["POST"])
@login_required
@permission_required(P.STOCK_MANAGE)
def check_entry_duplicate():
    product = db.session.get(Product, request.form.get("product_id", type=int))
    if product is None:
        return jsonify({"duplicate": False})
    quantity = dec(request.form.get("quantity"))
    unit_id = request.form.get("unit_id", type=int) or product.base_unit_id
    cost_unit = dec(request.form.get("cost")) if request.form.get("cost") else dec(product.cost_avg)
    lot_number = (request.form.get("lot_number") or "").strip() or None
    if request.form.get("allow_mod"):
        lot_number = (request.form.get("m_lot_number") or lot_number or "").strip() or None
        if request.form.get("m_cost"):
            cost_unit = dec(request.form.get("m_cost"))
    try:
        duplicate = stock_validation_service.find_duplicate_entry(
            product, quantity, unit_id, cost_unit, lot_number
        )
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    return jsonify(
        {
            "duplicate": duplicate is not None,
            "reference": duplicate.reference if duplicate else None,
        }
    )


def _stock_units():
    from app.models.catalog import Unit
    from app.services.seed import ensure_catalog_defaults

    ensure_catalog_defaults()
    return Unit.query.filter(Unit.product_id.is_(None)).order_by(Unit.label).all()


def _stock_categories():
    from app.models.catalog import Category
    from app.services.seed import ensure_catalog_defaults

    ensure_catalog_defaults()
    return Category.query.order_by(Category.name).all()


def _quick_create_product(user):
    """Crée un produit à la volée depuis l'écran d'entrée de stock.
    Si l'utilisateur n'a pas le droit de gérer les produits, le produit reste en attente.
    """
    from app.models.catalog import (
        Category,
        Product,
        ProductUnit,
        PRODUCT_PRESET_BASE_UNITS,
        PRODUCT_PRESET_UNIT_KINDS,
        Unit,
    )
    from app.security.permissions import P
    from app.services.product_units import parse_sale_unit_rows, save_product_sale_units

    name = (request.form.get("new_product_name") or "").strip()
    base_unit_id = request.form.get("new_base_unit_id", type=int)
    category_id = request.form.get("new_category_id", type=int)
    preset = (request.form.get("new_preset_type") or "").strip()
    if not name:
        return None
    if not base_unit_id:
        raise ValueError("Selectionnez une unite de stock.")
    if not category_id:
        raise ValueError("Selectionnez une categorie de produit.")
    base_unit = db.session.get(Unit, base_unit_id)
    if not preset or preset not in PRODUCT_PRESET_UNIT_KINDS:
        raise ValueError("Selectionnez un type de produit valide.")
    if base_unit is None or base_unit.product_id is not None:
        raise ValueError("Selectionnez une unite de stock partagee valide.")
    if base_unit.kind not in PRODUCT_PRESET_UNIT_KINDS[preset]:
        raise ValueError("L'unite de stock ne correspond pas au type de produit.")
    if base_unit.code != PRODUCT_PRESET_BASE_UNITS[preset]:
        raise ValueError("Choisissez la plus petite unite comme unite de comptage du stock.")
    if db.session.get(Category, category_id) is None:
        raise ValueError("La categorie selectionnee n'existe pas.")
    if Product.query.filter_by(
        category_id=category_id,
        normalized_name=normalize_product_name(name),
    ).first():
        raise ValueError("Un produit portant ce nom existe déjà dans cette catégorie.")
    sale_rows = parse_sale_unit_rows(request.form, "new_sale_unit", preset, base_unit)
    sale_unit_id = request.form.get("new_unite_vente_id", type=int)
    sale_unit = db.session.get(Unit, sale_unit_id) if sale_unit_id else None
    factor = dec(request.form.get("new_facteur"), default="1")
    if sale_unit_id and (
        sale_unit is None
        or sale_unit.product_id is not None
        or sale_unit.kind not in PRODUCT_PRESET_UNIT_KINDS[preset]
    ):
        raise ValueError("L'unite de vente selectionnee ne correspond pas au type de produit.")
    if sale_unit_id and sale_unit_id == base_unit_id:
        raise ValueError("L'unite de vente doit differer de l'unite de stock.")
    if sale_unit_id and factor <= 0:
        raise ValueError("Le facteur de conversion doit etre positif.")

    def _next_code():
        from app.models.base import utcnow
        today = utcnow().strftime("%y%m%d")
        count = Product.query.count() + 1
        return f"PRD-{today}-{count:04d}"

    code = _next_code()
    while Product.query.filter_by(code=code).first():
        import uuid
        code = f"PRD-{uuid.uuid4().hex[:8].upper()}"

    cost = dec(request.form.get("new_cost_avg"))
    currency = request.form.get("new_currency") or "CDF"
    is_perishable = bool(request.form.get("new_is_perishable"))
    track_lot = bool(request.form.get("new_track_lot"))
    default_expiry = None
    expiry_raw = request.form.get("new_expiry_date")
    if expiry_raw:
        try:
            from datetime import datetime
            default_expiry = datetime.strptime(expiry_raw, "%Y-%m-%d").date()
        except ValueError:
            default_expiry = None

    can_manage = user and user.has_permission(P.PRODUCTS_MANAGE)
    if can_manage:
        validation_status = ProductStatus.VALIDE
        active = True
        validated_by_id = user.id
        validated_at = utcnow()
    else:
        validation_status = ProductStatus.EN_ATTENTE
        active = False
        validated_by_id = None
        validated_at = None

    product = Product(
        code=code,
        name=name,
        base_unit_id=base_unit_id,
        category_id=category_id,
        currency=currency,
        kind=(request.form.get("new_kind") or "autre"),
        type_mesure=preset,
        cost_avg=cost,
        seuil_alerte=dec(request.form.get("new_seuil_alerte")),
        is_perishable=is_perishable,
        track_lot=track_lot or bool(default_expiry),
        default_expiry_date=default_expiry,
        active=active,
        validation_status=validation_status,
        proposed_by_id=user.id if user and not can_manage else None,
        validated_by_id=validated_by_id,
        validated_at=validated_at,
    )
    db.session.add(product)
    try:
        db.session.flush()
    except IntegrityError:
        db.session.rollback()
        raise ValueError("Un produit portant ce nom ou ce code existe déjà.") from None

    prix_vente = dec(request.form.get("new_prix_vente"))
    if prix_vente > 0:
        db.session.add(
            ProductUnit(
                product_id=product.id,
                unit_id=base_unit_id,
                factor=dec("1"),
                prix_vente=prix_vente,
                currency=currency,
                is_sale_default=True,
            )
        )

    if sale_unit_id:
        db.session.add(
            ProductUnit(
                product_id=product.id,
                unit_id=sale_unit_id,
                factor=factor,
                prix_vente=dec(request.form.get("new_prix_vente_unite")),
                currency=currency,
                is_sale_default=False,
            )
        )
    save_product_sale_units(product, sale_rows, currency)

    log_action(
        "product_create",
        entity="product",
        entity_uuid=product.uuid,
        after={"code": code, "name": name, "source": "stock_entry"},
        commit=False,
    )
    db.session.flush()
    return product, sale_rows



@stock_bp.route("/entrees-attente")
@login_required
@permission_required(P.STOCK_VIEW)
def entry_pending():
    status_filter = (request.args.get("statut") or "en_attente").strip().lower()
    query = StockEntryRequest.query
    if status_filter in ("en_attente", "validee", "rejetee"):
        query = query.filter_by(status=status_filter)
    pager = paginate(query.order_by(StockEntryRequest.created_at.desc()))
    return render_template(
        "stock/entry_pending.html",
        pager=pager,
        entries=pager.items,
        labels=STOCK_ENTRY_STATUS_LABELS,
        badges=STOCK_ENTRY_STATUS_BADGES,
        filter_status=status_filter,
    )


@stock_bp.route("/entrees-attente/<int:req_id>/modifier", methods=["POST"])
@login_required
@permission_required(P.STOCK_MANAGE)
@owner_reauth_required()
@owner_only()
def entry_update(req_id):
    req = db.session.get(StockEntryRequest, req_id) or abort(404)
    if req.status != StockEntryStatus.EN_ATTENTE:
        flash("Seule une demande en attente peut Ãªtre modifiÃ©e.", "warning")
        return redirect(url_for("stock.entry_pending"))

    qty_raw = (request.form.get("qty_base") or "").strip()
    cost_raw = (request.form.get("cost_unit") or "").strip()
    lot_raw = (request.form.get("lot_number") or "").strip()
    expiry_raw = request.form.get("expiry_date")
    reason = (request.form.get("reason") or "").strip() or req.reason
    notes = (request.form.get("notes") or "").strip() or None

    try:
        if qty_raw:
            qv = dec(qty_raw)
            if qv <= 0:
                raise ValueError("La quantitÃ© doit Ãªtre strictement positive.")
            req.qty_base = qv
            req.quantity = qv
        if cost_raw:
            cv = dec(cost_raw)
            if cv < 0:
                raise ValueError("Le coÃ»t unitaire ne peut pas Ãªtre nÃ©gatif.")
            req.cost_unit = cv
        req.lot_number = lot_raw or None
        if expiry_raw:
            try:
                from datetime import datetime
                req.expiry_date = datetime.strptime(expiry_raw, "%Y-%m-%d").date()
            except ValueError:
                req.expiry_date = None
        else:
            req.expiry_date = None
        req.reason = reason
        stock_validation_service.refresh_entry_duplicate_signature(req)
        log_action(
            "stock_entry_update",
            entity="stock_entry_request",
            entity_uuid=req.uuid,
            after={"product_id": req.product_id, "qty_base": str(req.qty_base), "lot_number": req.lot_number},
            reason=notes,
            commit=False,
        )
        db.session.commit()
        flash(f"Demande {req.reference} modifiÃ©e.", "success")
    except Exception as exc:
        db.session.rollback()
        flash(str(exc), "danger")
    return redirect(url_for("stock.entry_pending"))


@stock_bp.route('/entrees-attente/<int:req_id>/supprimer', methods=['POST'])
@login_required
@permission_required(P.STOCK_MANAGE)
@admin_password_required()
def entry_delete(req_id):
    req = db.session.get(StockEntryRequest, req_id) or abort(404)
    if req.status != StockEntryStatus.EN_ATTENTE:
        flash('Seule une demande en attente peut être supprimée.', 'warning')
        return redirect(url_for('stock.entry_pending'))

    try:
        ref = req.reference
        log_action(
            'stock_entry_delete',
            entity='stock_entry_request',
            entity_uuid=req.uuid,
            after={'product_id': req.product_id, 'qty_base': str(req.qty_base), 'status': req.status},
            commit=False,
        )
        db.session.delete(req)
        db.session.commit()
        flash(f'Demande {ref} supprimée.', 'success')
    except Exception as exc:
        db.session.rollback()
        flash(str(exc), 'danger')
    return redirect(url_for('stock.entry_pending'))


@stock_bp.route("/entrees-attente/<int:req_id>/valider", methods=["POST"])
@login_required
@owner_reauth_required()
@owner_only()
def entry_validate(req_id):
    req = db.session.get(StockEntryRequest, req_id) or abort(404)
    notes = (request.form.get("notes") or "").strip() or None

    lot_raw = (request.form.get("lot_number") or "").strip()
    if lot_raw:
        req.lot_number = lot_raw
    expiry_raw = request.form.get("expiry_date")
    if expiry_raw:
        try:
            from datetime import datetime
            req.expiry_date = datetime.strptime(expiry_raw, "%Y-%m-%d").date()
        except ValueError:
            pass

    try:
        stock_validation_service.refresh_entry_duplicate_signature(req)
        req, mv = stock_validation_service.validate_entry_request(req, current_user.id, notes=notes, commit=False)
        log_action(
            "stock_entry_validate",
            entity="stock_entry_request",
            entity_uuid=req.uuid,
            after={"product_id": req.product_id, "qty_base": str(req.qty_base), "validated_by": current_user.username},
            reason=notes,
            commit=False,
        )
        db.session.commit()
        flash(f"Entrée {req.reference} validée. Stock et coût moyen mis à jour.", "success")
    except ValueError as exc:
        db.session.rollback()
        flash(str(exc), "danger")
    except Exception as exc:
        db.session.rollback()
        flash(str(exc), "danger")
    return redirect(url_for("stock.entry_pending"))


@stock_bp.route("/entrees-attente/<int:req_id>/rejeter", methods=["POST"])
@login_required
@owner_reauth_required()
@owner_only()
def entry_reject(req_id):
    req = db.session.get(StockEntryRequest, req_id) or abort(404)
    reason = (request.form.get("reason") or request.form.get("reject_reason") or "").strip()
    if not reason:
        reason = "Rejeté par le propriétaire"
    try:
        stock_validation_service.reject_entry_request(req, current_user.id, reason, commit=False)
        log_action(
            "stock_entry_reject",
            entity="stock_entry_request",
            entity_uuid=req.uuid,
            after={"product_id": req.product_id},
            reason=reason,
            commit=False,
        )
        db.session.commit()
        flash(f"Entrée {req.reference} rejetée.", "warning")
    except ValueError as exc:
        db.session.rollback()
        flash(str(exc), "danger")
    return redirect(url_for("stock.entry_pending"))
