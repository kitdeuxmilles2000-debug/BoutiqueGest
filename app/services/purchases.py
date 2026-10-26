"""Logique d'achat / reception.

Cycle : brouillon -> commandee -> receptionnee. La reception cree les mouvements
de stock (KIND=reception) et met a jour le cout moyen pondere. Si l'achat est a
credit, une dette fournisseur (Credit type=fournisseur) est creee. L'annulation
d'une reception est une contre-ecriture tracee (stock inverse).
"""
from datetime import date
from decimal import Decimal

from app.extensions import db
from app.models.base import utcnow
from app.models.finance import CreditType
from app.models.purchases import Purchase, PurchaseLine, PurchaseStatus
from app.models.stock import MovementKind
from app.services import finance as finance_service
from app.services import notifications as notifications_service
from app.services.stock import conversion_factor, dec, record_movement


def next_purchase_reference(day=None):
    day = day or date.today()
    prefix = f"A-{day:%Y%m%d}"
    count = Purchase.query.filter(Purchase.reference.like(prefix + "%")).count()
    return f"{prefix}-{count + 1:04d}"


def create_purchase(
    *,
    supplier,
    currency,
    items,
    user_id,
    expected_date=None,
    paid_now=True,
    notes=None,
    commit=True,
):
    """Cree un achat en brouillon. `items` : [{product, unit_id, quantity, prix_unitaire}]."""
    purchase = Purchase(
        reference=next_purchase_reference(),
        supplier_id=supplier.id,
        currency=currency,
        status=PurchaseStatus.BROUILLON,
        expected_date=expected_date,
        paid_now=bool(paid_now),
        created_by_id=user_id,
        notes=(notes or "").strip() or None,
    )
    db.session.add(purchase)
    db.session.flush()

    total = Decimal("0")
    for item in items:
        product = item["product"]
        unit_id = item.get("unit_id")
        quantity = dec(item.get("quantity"))
        if quantity <= 0:
            continue
        factor = conversion_factor(product, unit_id)
        prix = dec(item.get("prix_unitaire"))
        db.session.add(
            PurchaseLine(
                purchase_id=purchase.id,
                product_id=product.id,
                unit_id=unit_id,
                quantity=quantity,
                qty_base=quantity * factor,
                prix_unitaire=prix,
                currency=currency,
            )
        )
        total += quantity * prix

    purchase.montant_total = total
    if commit:
        db.session.commit()
    return purchase


def mark_ordered(purchase, commit=True):
    if purchase.status != PurchaseStatus.BROUILLON:
        raise ValueError("Seul un brouillon peut etre commande.")
    purchase.status = PurchaseStatus.COMMANDE
    if commit:
        db.session.commit()
    return purchase


def receive_purchase(purchase, user_id, *, cash_session=None, commit=True):
    """Receptionne un achat : entree en stock + dette fournisseur si a credit."""
    if purchase.status == PurchaseStatus.RECEPTIONNEE:
        raise ValueError("Cet achat est deja receptionne.")
    if purchase.status == PurchaseStatus.ANNULEE:
        raise ValueError("Cet achat est annule.")

    for line in purchase.lines:
        factor = conversion_factor(line.product, line.unit_id)
        cost_base = (dec(line.prix_unitaire) / factor) if factor > 0 else dec(line.prix_unitaire)
        record_movement(
            line.product,
            MovementKind.RECEPTION,
            dec(line.qty_base),
            unit_id=line.unit_id,
            cost_unit=cost_base,
            currency=purchase.currency,
            source_type="purchase",
            source_uuid=purchase.uuid,
            reason=f"Achat {purchase.reference}",
            user_id=user_id,
            commit=False,
        )

    purchase.status = PurchaseStatus.RECEPTIONNEE
    purchase.received_at = utcnow()
    purchase.validated_by_id = user_id

    # Notifications : stock remis à niveau suite à la réception validée
    for line in purchase.lines:
        if dec(line.qty_base) <= 0:
            continue
        notifications_service.notify_stock_replenished(
            line.product, source=purchase.reference, commit=False
        )

    if not purchase.paid_now:
        finance_service.create_credit(
            credit_type=CreditType.FOURNISSEUR,
            amount=purchase.montant_total,
            currency=purchase.currency,
            supplier=purchase.supplier,
            due_date=purchase.expected_date,
            notes=f"Achat {purchase.reference}",
            user_id=user_id,
            commit=False,
        )

    if commit:
        db.session.commit()
    return purchase


def cancel_purchase(purchase, user_id, reason, *, restock=True, commit=True):
    """Annule un achat. Si receptionne, contre-ecrit le stock (retour fournisseur)."""
    if purchase.status == PurchaseStatus.ANNULEE:
        raise ValueError("Cet achat est deja annule.")

    if purchase.status == PurchaseStatus.RECEPTIONNEE and restock:
        for line in purchase.lines:
            if dec(line.qty_base) == 0:
                continue
            record_movement(
                line.product,
                MovementKind.RETOUR,
                -dec(line.qty_base),
                unit_id=line.unit_id,
                currency=purchase.currency,
                source_type="purchase_cancel",
                source_uuid=purchase.uuid,
                reason=f"Annulation achat {purchase.reference}",
                user_id=user_id,
                commit=False,
            )

    purchase.status = PurchaseStatus.ANNULEE
    purchase.cancelled_by_id = user_id
    purchase.cancelled_at = utcnow()
    purchase.cancel_reason = (reason or "").strip() or None
    purchase.notes = (f"{purchase.notes or ''}\nAnnule : {reason}").strip()
    if commit:
        db.session.commit()
    return purchase
