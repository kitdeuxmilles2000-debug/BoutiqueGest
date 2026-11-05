"""Validation des entrées de stock par le propriétaire.

Les entrées saisies par vendeurs/responsables sont mises en "attente de validation".
Elles ne modifient PAS le stock, le CMP ni la valeur tant que le propriétaire
ne les valide pas après contrôle physique.
"""
from datetime import date, datetime, time, timedelta
from decimal import Decimal, ROUND_HALF_UP
import hashlib
import json

from app.extensions import db
from app.models.base import utcnow
from app.models.stock import (
    Batch,
    MovementKind,
    StockEntryRequest,
    StockEntryStatus,
)
from app.services.stock import conversion_factor, dec, record_movement


def _quantity_base(quantity, factor):
    return (dec(quantity) * factor).quantize(Decimal("0.001"), rounding=ROUND_HALF_UP)


def _unit_cost(cost):
    return dec(cost).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def _duplicate_signature(product_id, qty_base, cost_base, lot_number, day):
    values = (
        product_id,
        format(dec(qty_base).normalize(), "f"),
        format(dec(cost_base).normalize(), "f"),
        (lot_number or "").strip().casefold(),
        day.isoformat(),
    )
    return hashlib.sha256(json.dumps(values, ensure_ascii=False).encode("utf-8")).hexdigest()


def refresh_entry_duplicate_signature(entry_req):
    """Keep the database fingerprint aligned when an entry is edited."""
    if entry_req.duplicate_approved_by_id or not entry_req.duplicate_signature:
        entry_req.duplicate_signature = None
        return
    factor = conversion_factor(entry_req.product, entry_req.unit_id)
    cost_base = _unit_cost(entry_req.cost_unit) / factor if factor else _unit_cost(entry_req.cost_unit)
    entry_req.duplicate_signature = _duplicate_signature(
        entry_req.product_id,
        _quantity_base(entry_req.qty_base, Decimal("1")),
        cost_base,
        entry_req.lot_number,
        entry_req.created_at.date(),
    )


def find_duplicate_entry(product, quantity, unit_id, cost_unit, lot_number, *, day=None):
    """Find a same-day pending or validated entry with equivalent base quantities."""
    day = day or utcnow().date()
    start = datetime.combine(day, time.min)
    end = start + timedelta(days=1)
    factor = conversion_factor(product, unit_id)
    qty_base = _quantity_base(quantity, factor)
    cost_base = _unit_cost(cost_unit) / factor if factor else _unit_cost(cost_unit)
    candidates = StockEntryRequest.query.filter(
        StockEntryRequest.product_id == product.id,
        StockEntryRequest.created_at >= start,
        StockEntryRequest.created_at < end,
        StockEntryRequest.status.in_((StockEntryStatus.EN_ATTENTE, StockEntryStatus.VALIDEE)),
        StockEntryRequest.qty_base == dec(qty_base),
    ).all()
    target_lot = (lot_number or "").strip().casefold()
    for candidate in candidates:
        try:
            factor = conversion_factor(product, candidate.unit_id)
        except ValueError:
            continue
        candidate_cost_base = dec(candidate.cost_unit) / factor if factor else dec(candidate.cost_unit)
        if (
            candidate_cost_base == dec(cost_base)
            and (candidate.lot_number or "").strip().casefold() == target_lot
        ):
            return candidate
    return None


def next_entry_reference(day=None):
    day = day or date.today()
    prefix = f"ENT-{day:%Y%m%d}"
    count = StockEntryRequest.query.filter(StockEntryRequest.reference.like(prefix + "%")).count()
    return f"{prefix}-{count + 1:04d}"


def create_entry_request(
    *,
    product,
    quantity,
    unit_id,
    cost_unit,
    currency,
    reason=None,
    notes=None,
    lot_number=None,
    expiry_date=None,
    supplier_id=None,
    purchase_id=None,
    user_id,
    duplicate_approved_by_id=None,
    commit=True,
):
    qty = dec(quantity)
    if qty <= 0:
        raise ValueError("La quantité doit être strictement positive.")
    factor = conversion_factor(product, unit_id)
    qty_base = _quantity_base(qty, factor)
    if qty_base <= 0:
        raise ValueError("La quantité est trop petite pour être enregistrée dans l'unité de stock.")
    cost = _unit_cost(cost_unit)
    created_at = utcnow()
    cost_base = cost / factor if factor else cost

    req = StockEntryRequest(
        reference=next_entry_reference(),
        product_id=product.id,
        currency=currency,
        status=StockEntryStatus.EN_ATTENTE,
        quantity=qty,
        unit_id=unit_id,
        qty_base=qty_base,
        cost_unit=cost,
        reason=(reason or "").strip() or None,
        notes=(notes or "").strip() or None,
        lot_number=(lot_number or "").strip() or None,
        expiry_date=expiry_date,
        supplier_id=supplier_id,
        purchase_id=purchase_id,
        created_by_id=user_id,
        created_at=created_at,
        duplicate_signature=(
            None
            if duplicate_approved_by_id
            else _duplicate_signature(
                product.id, qty_base, cost_base, lot_number, created_at.date()
            )
        ),
        duplicate_approved_by_id=duplicate_approved_by_id,
    )
    db.session.add(req)
    if commit:
        db.session.commit()
    return req


def validate_entry_request(entry_req, user_id, *, notes=None, commit=True):
    """Valide une entrée en attente après contrôle physique.

    Seul le propriétaire doit appeler cette fonction (route protégée).
    À la validation : mouvement de stock + mise à jour lot/péremption + CMP.
    Si le produit est en attente de validation, il est validé automatiquement.
    """
    if entry_req.status != StockEntryStatus.EN_ATTENTE:
        raise ValueError("Cette demande n'est plus en attente de validation.")
    if dec(entry_req.qty_base) <= 0:
        raise ValueError("Quantité invalide.")

    product = entry_req.product
    from app.models.catalog import ProductStatus
    if product and getattr(product, "validation_status", None) == ProductStatus.EN_ATTENTE:
        product.validation_status = ProductStatus.VALIDE
        product.active = True
        product.validated_by_id = user_id
        product.validated_at = utcnow()
        if notes and not getattr(product, "validation_note", None):
            product.validation_note = notes

    # Créer lot si périssable avec lot/date
    batch = None
    if entry_req.lot_number or entry_req.expiry_date:
        batch = Batch(
            product_id=entry_req.product_id,
            lot_number=entry_req.lot_number,
            expiry_date=entry_req.expiry_date,
            qty_remaining=Decimal("0"),
            cost_unit=entry_req.cost_unit,
        )
        db.session.add(batch)
        db.session.flush()

    # Appliquer le mouvement de stock (augmente stock, met à jour CMP)
    mv = record_movement(
        entry_req.product,
        MovementKind.RECEPTION,
        dec(entry_req.qty_base),
        unit_id=entry_req.unit_id,
        cost_unit=(dec(entry_req.cost_unit) / conversion_factor(entry_req.product, entry_req.unit_id))
        if conversion_factor(entry_req.product, entry_req.unit_id) > 0
        else dec(entry_req.cost_unit),
        currency=entry_req.currency,
        source_type="stock_entry_request",
        source_uuid=entry_req.uuid,
        reason=entry_req.reason or f"Entrée validée {entry_req.reference}",
        user_id=user_id,
        batch=batch,
        commit=False,
    )
    mv.stock_entry_request_id = entry_req.id

    entry_req.status = StockEntryStatus.VALIDEE
    entry_req.validated_by_id = user_id
    entry_req.validated_at = utcnow()
    if notes:
        entry_req.notes = ((entry_req.notes or "") + f"\nValidation : {notes}").strip()

    if commit:
        db.session.commit()
    return entry_req, mv


def reject_entry_request(entry_req, user_id, reason, *, commit=True):
    if entry_req.status != StockEntryStatus.EN_ATTENTE:
        raise ValueError("Cette demande n'est plus en attente de validation.")
    if not (reason or "").strip():
        raise ValueError("Un motif de rejet est obligatoire.")
    entry_req.status = StockEntryStatus.REJETEE
    entry_req.rejected_by_id = user_id
    entry_req.rejected_at = utcnow()
    entry_req.reject_reason = (reason or "").strip()
    entry_req.duplicate_signature = None
    if commit:
        db.session.commit()
    return entry_req
