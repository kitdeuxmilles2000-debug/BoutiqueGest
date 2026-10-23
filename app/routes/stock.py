"""Stock : vue d'ensemble, mouvements, entrees, pertes, inventaires et validations."""
from datetime import date

from flask import Blueprint, abort, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required

from app.extensions import db
from app.models.catalog import Product
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
from app.security.decorators import owner_only, owner_reauth_required, permission_required
from app.security.permissions import P
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
    total_value = sum((p.stock_value for p in products), start=dec(0))
    return render_template(
        "stock/index.html",
        products=products,
        alerts=alerts,
        total_value=total_value,
    )


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
    movements = query.order_by(StockMovement.created_at.desc()).limit(300).all()
    return render_template(
        "stock/movements.html",
        movements=movements,
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

        # Creation directe d'un produit par l'administrateur/proprietaire
        if product is None and (request.form.get("new_product_name") or "").strip():
            product = _quick_create_product(current_user)
            if product is None:
                flash("Création du produit impossible : vérifiez nom, unité de stock et prix.", "danger")
                return redirect(url_for("stock.entry"))
            qty_raw_q = (request.form.get("new_qty_initial") or "").strip()
            if qty_raw_q:
                quantity_new = dec(qty_raw_q)
                if quantity_new <= 0:
                    flash("La quantité à entrer doit être positive.", "danger")
                    return redirect(url_for("stock.entry"))
                unit_id = unit_id or product.base_unit_id
                cost_unit = cost_unit or dec(product.cost_avg)
                quantity = quantity_new

        if product is None:
            flash("Produit introuvable.", "danger")
            return redirect(url_for("stock.entry"))
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
            db.session.commit()
            flash(
                f"Demande d'entrée {req.reference} soumise. En attente de validation par le propriétaire.",
                "success",
            )
        except ValueError as exc:
            db.session.rollback()
            flash(str(exc), "danger")
            return redirect(url_for("stock.entry"))

        return redirect(url_for("stock.entry_pending"))

    return render_template(
        "stock/entry.html",
        products=products,
        pending_qty=pending_qty,
        suppliers=Supplier.query.order_by(Supplier.name).all(),
        units=_stock_units(),
        categories=_stock_categories(),
        can_create=current_user.has_permission(P.PRODUCTS_MANAGE),
    )


def _stock_units():
    from app.models.catalog import Unit

    return Unit.query.order_by(Unit.label).all()


def _stock_categories():
    from app.models.catalog import Category

    return Category.query.order_by(Category.name).all()


def _quick_create_product(user):
    """Cree un produit a la volee depuis l'ecran d'entree de stock.

    Reserve aux profils ayant la permission de gerer les produits (administrateur).
    """
    from app.models.catalog import Category, Product, ProductUnit

    name = (request.form.get("new_product_name") or "").strip()
    base_unit_id = request.form.get("new_base_unit_id", type=int)
    if not name or not base_unit_id:
        return None

    code = (request.form.get("new_code") or "").strip().upper()
    if not code:
        today = utcnow().strftime("%y%m%d")
        count = Product.query.count() + 1
        code = f"PRD-{today}-{count:04d}"
    if Product.query.filter_by(code=code).first():
        today = utcnow().strftime("%y%m%d")
        count = Product.query.count() + 1
        code = f"PRD-{today}-{count:04d}"

    cost = dec(request.form.get("new_cost_avg"))
    currency = request.form.get("new_currency") or "CDF"
    category_id = request.form.get("new_category_id", type=int) or None
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
    shelf_raw = (request.form.get("new_shelf_life_days") or "").strip()
    shelf_life = int(shelf_raw) if shelf_raw.isdigit() and int(shelf_raw) > 0 else None

    product = Product(
        code=code,
        name=name,
        base_unit_id=base_unit_id,
        category_id=category_id,
        currency=currency,
        kind=(request.form.get("new_kind") or "autre"),
        cost_avg=cost,
        seuil_alerte=dec(request.form.get("new_seuil_alerte")),
        is_perishable=is_perishable,
        track_lot=track_lot or bool(default_expiry),
        default_expiry_date=default_expiry,
        shelf_life_days=shelf_life,
        active=True,
    )
    db.session.add(product)
    db.session.flush()

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

    unite_vente_id = request.form.get("new_unite_vente_id", type=int)
    if unite_vente_id and unite_vente_id != base_unit_id:
        db.session.add(
            ProductUnit(
                product_id=product.id,
                unit_id=unite_vente_id,
                factor=dec(request.form.get("new_facteur"), default="1"),
                prix_vente=dec(request.form.get("new_prix_vente_unite")),
                currency=currency,
                is_sale_default=False,
            )
        )

    log_action(
        "product_create",
        entity="product",
        entity_uuid=product.uuid,
        after={"code": code, "name": name, "source": "stock_entry"},
        commit=False,
    )
    db.session.flush()
    return product



@stock_bp.route("/entrees-attente")
@login_required
@permission_required(P.STOCK_VIEW)
def entry_pending():
    status_filter = (request.args.get("statut") or "en_attente").strip().lower()
    query = StockEntryRequest.query
    if status_filter in ("en_attente", "validee", "rejetee"):
        query = query.filter_by(status=status_filter)
    entries = query.order_by(StockEntryRequest.created_at.desc()).limit(300).all()
    return render_template(
        "stock/entry_pending.html",
        entries=entries,
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
@owner_reauth_required()
@owner_only()
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
