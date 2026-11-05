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
    if pu is None:
        raise ValueError("Cette unite n'est pas associee au produit selectionne.")
    return pu.factor


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


def stock_financial_summary(products):
    """Valorise le stock et estime sa marge brute par devise et produit."""
    totals = {}
    product_margins = {}
    for product in products:
        quantity = dec(product.stock_qty)
        stock_value = dec(product.stock_value)
        currency = product.currency
        currency_totals = totals.setdefault(
            currency,
            {"stock_value": Decimal("0"), "potential_margin": Decimal("0"), "priced_products": 0},
        )
        currency_totals["stock_value"] += stock_value

        sale_units = [
            unit
            for unit in product.selling_units
            if (
                unit.active
                and unit.currency == currency
                and dec(unit.factor) > 0
                and dec(unit.prix_vente) > 0
            )
        ]
        sale_unit = next((unit for unit in sale_units if unit.is_sale_default), None)
        sale_unit = sale_unit or (sale_units[0] if sale_units else None)
        if sale_unit is None:
            product_margins[product.id] = None
            continue

        factor = dec(sale_unit.factor)
        estimated_revenue = quantity * dec(sale_unit.prix_vente) / factor
        potential_margin = estimated_revenue - stock_value
        currency_totals["potential_margin"] += potential_margin
        currency_totals["priced_products"] += 1
        product_margins[product.id] = {
            "unit_label": sale_unit.unit.label,
            "unit_price": dec(sale_unit.prix_vente),
            "margin": potential_margin,
            "margin_percent": (
                potential_margin * Decimal("100") / estimated_revenue
                if estimated_revenue > 0
                else None
            ),
        }

    return totals, product_margins


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
