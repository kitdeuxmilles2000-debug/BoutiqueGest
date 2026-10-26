"""Suppression definitive d'un produit et de toutes ses operations liees.

La suppression est irreversible : ventes, paiements, remboursements, mouvements
de caisse, credits, mouvements de stock, lots, demandes d'entree, lignes
d'inventaire et lignes d'achat lies au produit sont supprimes.
"""
from decimal import Decimal

from app.extensions import db
from app.models.catalog import PriceHistory, Product, ProductUnit
from app.models.finance import Credit, Settlement
from app.models.notifications import Notification
from app.models.purchases import Purchase, PurchaseLine
from app.models.sales import CashMovement, Payment, Refund, Sale, SaleLine
from app.models.stock import (
    Batch,
    InventoryLine,
    StockEntryRequest,
    StockMovement,
)
from app.services.stock import dec


def _sale_ids(product):
    rows = (
        db.session.query(SaleLine.sale_id)
        .filter(SaleLine.product_id == product.id)
        .distinct()
        .all()
    )
    return [row[0] for row in rows]


def collect_impact(product):
    """Resume de ce qui sera supprime avec le produit."""
    sale_ids = _sale_ids(product)
    sales = Sale.query.filter(Sale.id.in_(sale_ids)).all() if sale_ids else []
    sale_uuids = [s.uuid for s in sales]
    sale_line_ids = [line.id for sale in sales for line in sale.lines]

    credits = Credit.query.filter(Credit.sale_id.in_(sale_ids)).all() if sale_ids else []
    credit_ids = [c.id for c in credits]
    settlements = (
        Settlement.query.filter(Settlement.credit_id.in_(credit_ids)).all()
        if credit_ids
        else []
    )
    settlement_uuids = [s.uuid for s in settlements]

    cash_source_uuids = sale_uuids + settlement_uuids
    cash_movements = (
        CashMovement.query.filter(CashMovement.source_uuid.in_(cash_source_uuids)).all()
        if cash_source_uuids
        else []
    )

    purchase_lines = PurchaseLine.query.filter_by(product_id=product.id).all()
    purchase_ids = {line.purchase_id for line in purchase_lines}
    empty_purchase_ids = set()
    for purchase_id in purchase_ids:
        remaining = (
            PurchaseLine.query.filter(
                PurchaseLine.purchase_id == purchase_id,
                PurchaseLine.product_id != product.id,
            ).count()
        )
        if remaining == 0:
            empty_purchase_ids.add(purchase_id)

    return {
        "stock_qty": dec(product.stock_qty),
        "pending_entries": StockEntryRequest.query.filter_by(product_id=product.id).count(),
        "movements": StockMovement.query.filter_by(product_id=product.id).count(),
        "batches": Batch.query.filter_by(product_id=product.id).count(),
        "inventory_lines": InventoryLine.query.filter_by(product_id=product.id).count(),
        "purchase_lines": len(purchase_lines),
        "purchases_removed": len(empty_purchase_ids),
        "sales": len(sales),
        "sale_lines": len(sale_line_ids),
        "payments": sum(len(s.payments) for s in sales),
        "refunds": sum(len(s.refunds) for s in sales),
        "credits": len(credits),
        "settlements": len(settlements),
        "cash_movements": len(cash_movements),
        "price_history": PriceHistory.query.filter_by(product_id=product.id).count(),
        "product_units": ProductUnit.query.filter_by(product_id=product.id).count(),
        "notifications": Notification.query.filter_by(
            entity_type="product", entity_id=product.id
        ).count(),
        "has_operations": bool(
            sales
            or cash_movements
            or credits
            or purchase_lines
            or StockMovement.query.filter_by(product_id=product.id).count()
        ),
    }


def delete_product(product, *, commit=True):
    """Supprime le produit et toutes ses operations liees.

    Retourne le resume de l'impact effectivement supprime.
    """
    impact = collect_impact(product)
    product_id = product.id

    sale_ids = _sale_ids(product)
    sales = Sale.query.filter(Sale.id.in_(sale_ids)).all() if sale_ids else []
    sale_uuids = [s.uuid for s in sales]

    credits = Credit.query.filter(Credit.sale_id.in_(sale_ids)).all() if sale_ids else []
    credit_ids = [c.id for c in credits]
    settlements = (
        Settlement.query.filter(Settlement.credit_id.in_(credit_ids)).all()
        if credit_ids
        else []
    )
    settlement_uuids = [s.uuid for s in settlements]

    cash_source_uuids = sale_uuids + settlement_uuids
    if cash_source_uuids:
        CashMovement.query.filter(CashMovement.source_uuid.in_(cash_source_uuids)).delete(
            synchronize_session=False
        )

    for credit in credits:
        db.session.delete(credit)

    if sale_ids:
        Sale.query.filter(Sale.sale_origine_id.in_(sale_ids)).update(
            {"sale_origine_id": None}, synchronize_session=False
        )
        for sale in sales:
            db.session.delete(sale)

    StockMovement.query.filter_by(product_id=product_id).delete(synchronize_session=False)
    StockEntryRequest.query.filter_by(product_id=product_id).delete(synchronize_session=False)
    Batch.query.filter_by(product_id=product_id).delete(synchronize_session=False)
    InventoryLine.query.filter_by(product_id=product_id).delete(synchronize_session=False)

    purchase_lines = PurchaseLine.query.filter_by(product_id=product_id).all()
    purchase_ids = {line.purchase_id for line in purchase_lines}
    for line in purchase_lines:
        db.session.delete(line)
    db.session.flush()
    for purchase_id in purchase_ids:
        purchase = db.session.get(Purchase, purchase_id)
        if purchase is None:
            continue
        remaining = [line for line in purchase.lines if line.product_id != product_id]
        if remaining:
            purchase.montant_total = sum(
                (dec(line.quantity) * dec(line.prix_unitaire) for line in remaining),
                Decimal("0"),
            )
        else:
            StockEntryRequest.query.filter_by(purchase_id=purchase_id).update(
                {"purchase_id": None}, synchronize_session=False
            )
            db.session.delete(purchase)

    PriceHistory.query.filter_by(product_id=product_id).delete(synchronize_session=False)
    Notification.query.filter_by(entity_type="product", entity_id=product_id).delete(
        synchronize_session=False
    )

    db.session.delete(product)
    db.session.flush()
    if commit:
        db.session.commit()
    return impact
