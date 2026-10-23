"""Logique de stock : conversions, mouvements, cout moyen pondere, inventaires."""
from decimal import Decimal, InvalidOperation

from app.extensions import db
from app.models.catalog import Product, ProductUnit
from app.models.stock import IN_KINDS, InventoryLine, MovementKind, StockMovement


def dec(value, default="0"):
    """Convertit une valeur en Decimal de facon sure."""
    if value is None or value == "":
        return Decimal(default)
    if isinstance(value, Decimal):
        return value
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError):
        return Decimal(default)


def conversion_factor(product, unit_id):
    """Facteur vers l'unite de base (1 <unite> = factor <base>)."""
    if unit_id is None or unit_id == product.base_unit_id:
        return Decimal("1")
    pu = ProductUnit.query.filter_by(product_id=product.id, unit_id=unit_id).first()
    return pu.factor if pu else Decimal("1")


def to_base_quantity(product, unit_id, quantity):
    return dec(quantity) * conversion_factor(product, unit_id)


def record_movement(
    product,
    kind,
    quantity_base,
    *,
    unit_id=None,
    cost_unit=None,
    currency=None,
    source_type=None,
    source_uuid=None,
    reason=None,
    user_id=None,
    batch=None,
    commit=True,
):
    """Enregistre un mouvement de stock et met a jour quantite + cout moyen.

    quantity_base est signee (positive = entree, negative = sortie) et exprimee
    dans l'unite de base du produit.
    """
    qty = dec(quantity_base)
    if qty == 0:
        raise ValueError("La quantite du mouvement ne peut pas etre nulle.")

    factor = conversion_factor(product, unit_id) if unit_id else Decimal("1")
    cost = dec(cost_unit) if cost_unit is not None else None

    movement = StockMovement(
        product_id=product.id,
        kind=kind,
        quantity=qty,
        unit_id=unit_id,
        unit_factor=factor,
        cost_unit=cost,
        currency=currency or product.currency,
        source_type=source_type,
        source_uuid=source_uuid,
        reason=reason,
        user_id=user_id,
        batch_id=batch.id if batch else None,
    )
    db.session.add(movement)

    old_qty = dec(product.stock_qty)
    new_qty = old_qty + qty

    # Mise a jour du cout moyen pondere sur les entrees valorisees
    if kind in IN_KINDS and cost is not None and qty > 0:
        old_cmp = dec(product.cost_avg)
        total_value = old_qty * old_cmp + qty * cost
        product.cost_avg = (total_value / new_qty) if new_qty > 0 else cost

    product.stock_qty = new_qty

    if batch is not None:
        batch.qty_remaining = dec(batch.qty_remaining) + qty

    if commit:
        db.session.commit()
    return movement


def recompute_stock(product):
    """Recalcule la quantite a partir des mouvements (controle / reparation)."""
    total = sum((dec(m.quantity) for m in product_movements(product)), Decimal("0"))
    product.stock_qty = total
    db.session.commit()
    return total


def product_movements(product):
    return (
        StockMovement.query.filter_by(product_id=product.id)
        .order_by(StockMovement.created_at.desc())
        .all()
    )


def apply_inventory_validation(session, user_id, reason=None):
    """Applique les ecarts d'un inventaire valide sous forme de mouvements."""
    created = 0
    for line in session.lines:
        ecart = dec(line.qty_comptee) - dec(line.qty_theorique)
        line.ecart = ecart
        line.ecart_valeur = ecart * dec(line.product.cost_avg)
        if ecart == 0:
            continue
        record_movement(
            line.product,
            MovementKind.CORRECTION_INVENTAIRE,
            ecart,
            source_type="inventory",
            source_uuid=session.uuid,
            reason=reason or line.reason or f"Inventaire {session.reference}",
            user_id=user_id,
            commit=False,
        )
        created += 1
    db.session.commit()
    return created


def stock_alerts(products=None):
    """Retourne les produits en rupture, stock bas ou perimes proches."""
    from datetime import date, timedelta

    from app.models.stock import Batch

    products = products if products is not None else Product.query.filter_by(active=True).all()
    out_of_stock = [p for p in products if p.is_out_of_stock]
    low_stock = [p for p in products if p.is_low_stock]

    soon = date.today() + timedelta(days=30)
    expiring = (
        Batch.query.filter(
            Batch.active.is_(True),
            Batch.expiry_date.isnot(None),
            Batch.expiry_date <= soon,
        )
        .order_by(Batch.expiry_date)
        .all()
    )
    return {
        "out_of_stock": out_of_stock,
        "low_stock": low_stock,
        "expiring": expiring,
    }
