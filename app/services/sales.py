"""Logique de vente : creation, validation, annulation, remboursement.

Une vente validee est **immuable** : on ne la modifie ni ne la supprime. Toute
correction passe par une contre-ecriture (annulation / remboursement) tracee.
"""
from datetime import date
from decimal import Decimal

from app.extensions import db
from app.models.catalog import ProductUnit
from app.models.sales import (
    CashMovementKind,
    Payment,
    PaymentMethod,
    Refund,
    Sale,
    SaleLine,
    SaleStatus,
)
from app.models.stock import MovementKind
from app.models.sync import enqueue
from app.services import cash as cash_service
from app.services.stock import conversion_factor, dec, record_movement


class StockInsuffisant(ValueError):
    """Le stock disponible (valide) ne couvre pas la quantite demandee."""


def _queue_sync(entity, action, entity_uuid, payload=None, author_id=None):
    import json

    enqueue(
        entity,
        action,
        entity_uuid=entity_uuid,
        payload=json.dumps(payload) if payload else None,
        author_id=author_id,
    )


def next_sale_number(day=None):
    day = day or date.today()
    prefix = f"V-{day:%Y%m%d}"
    count = Sale.query.filter(Sale.numero.like(prefix + "%")).count()
    return f"{prefix}-{count + 1:04d}"


def unit_price(product, unit_id, currency=None):
    """Prix de vente catalogue pour un produit et une unite (0 si non defini)."""
    pu = ProductUnit.query.filter_by(product_id=product.id, unit_id=unit_id).first()
    if pu is not None and (currency is None or pu.currency == currency):
        return dec(pu.prix_vente)
    if pu is not None:
        return dec(pu.prix_vente)
    return dec(0)


def sellable_units(product, currency):
    """Unites de vente du produit dans la devise demandee."""
    return [pu for pu in product.selling_units if pu.currency == currency]


def create_sale(
    vendeur_id,
    cash_session,
    currency,
    items,
    *,
    remise=0,
    payments=None,
    notes=None,
    commit=True,
):
    """Cree une vente validee avec ses lignes, mouvements de stock et encaissements.

    `items` : liste de dicts {product, unit_id, quantity, prix_unitaire?}.
    `payments` : liste de dicts {amount, method, reference?}.
    """
    sale = Sale(
        numero=next_sale_number(),
        vendeur_id=vendeur_id,
        cash_session_id=cash_session.id if cash_session else None,
        currency=currency,
        status=SaleStatus.VALIDEE,
        remise=dec(remise),
        notes=(notes or "").strip() or None,
    )
    db.session.add(sale)
    db.session.flush()

    subtotal = Decimal("0")
    # Verification du stock disponible AVANT tout mouvement : un produit sans
    # stock valide ne peut pas etre vendu (le stock ne bouge qu'apres
    # validation d'une entree par le proprietaire).
    for item in items:
        product = item["product"]
        unit_id = item.get("unit_id")
        quantity = dec(item.get("quantity"))
        if quantity <= 0:
            continue
        factor = conversion_factor(product, unit_id)
        qty_base = quantity * factor
        disponible = dec(product.stock_qty)
        if disponible < qty_base:
            raise StockInsuffisant(
                f"Stock insuffisant pour {product.name} : "
                f"{disponible} {product.base_unit.label if product.base_unit else ''} "
                f"disponibles, {qty_base} demandés. "
                f"Validez une entrée de stock avant de vendre ce produit."
            )

    for item in items:
        product = item["product"]
        unit_id = item.get("unit_id")
        quantity = dec(item.get("quantity"))
        if quantity <= 0:
            continue

        factor = conversion_factor(product, unit_id)
        qty_base = quantity * factor
        prix = dec(item.get("prix_unitaire")) if item.get("prix_unitaire") is not None else unit_price(
            product, unit_id, currency
        )
        cout = dec(product.cost_avg)

        db.session.add(
            SaleLine(
                sale_id=sale.id,
                product_id=product.id,
                unit_id=unit_id,
                quantity=quantity,
                qty_base=qty_base,
                prix_unitaire=prix,
                cout_unitaire_cmp=cout,
                currency=currency,
            )
        )
        subtotal += quantity * prix

        record_movement(
            product,
            MovementKind.VENTE,
            -qty_base,
            unit_id=unit_id,
            cost_unit=cout,
            currency=currency,
            source_type="sale",
            source_uuid=sale.uuid,
            reason=f"Vente {sale.numero}",
            user_id=vendeur_id,
            commit=False,
        )

    sale.montant_total = subtotal - dec(remise)

    paid = Decimal("0")
    for pay in payments or []:
        amount = dec(pay.get("amount"))
        if amount <= 0:
            continue
        method = pay.get("method") or PaymentMethod.ESPECE
        db.session.add(
            Payment(
                sale_id=sale.id,
                amount=amount,
                currency=currency,
                method=method,
                reference=(pay.get("reference") or "").strip() or None,
                user_id=vendeur_id,
            )
        )
        paid += amount
        if method == PaymentMethod.ESPECE and cash_session is not None:
            cash_service.record_cash(
                cash_session,
                CashMovementKind.VENTE,
                amount,
                source_type="sale",
                source_uuid=sale.uuid,
                reason=f"Vente {sale.numero}",
                user_id=vendeur_id,
                commit=False,
            )

    sale.montant_paye = paid
    _queue_sync(
        "sale",
        "create",
        sale.uuid,
        payload={
            "numero": sale.numero,
            "currency": currency,
            "montant_total": str(sale.montant_total),
            "montant_paye": str(paid),
        },
        author_id=vendeur_id,
    )
    if commit:
        db.session.commit()
    return sale


def _reverse_stock(sale, user_id, reason, restock=True):
    if not restock:
        return
    for line in sale.lines:
        if dec(line.qty_base) == 0:
            continue
        record_movement(
            line.product,
            MovementKind.RETOUR,
            dec(line.qty_base),
            unit_id=line.unit_id,
            currency=sale.currency,
            source_type="sale_cancel",
            source_uuid=sale.uuid,
            reason=reason,
            user_id=user_id,
            commit=False,
        )


def _reverse_cash(sale, user_id, reason, amount=None):
    if sale.cash_session is None:
        return
    montant = dec(amount) if amount is not None else dec(sale.montant_paye)
    if montant <= 0:
        return
    cash_service.record_cash(
        sale.cash_session,
        CashMovementKind.REMBOURSEMENT,
        -montant,
        source_type="sale_cancel",
        source_uuid=sale.uuid,
        reason=reason,
        user_id=user_id,
        commit=False,
    )


def cancel_sale(sale, user_id, reason, restock=True, commit=True):
    """Annule une vente validee (contre-ecriture stock + caisse). La vente reste tracee."""
    if sale.status != SaleStatus.VALIDEE:
        raise ValueError("Seule une vente validee peut etre annulee.")

    _reverse_stock(sale, user_id, reason, restock=restock)
    _reverse_cash(sale, user_id, reason)
    sale.status = SaleStatus.ANNULEE
    sale.notes = (f"{sale.notes or ''}\nAnnulee : {reason}").strip()
    _queue_sync("sale", "cancel", sale.uuid, payload={"reason": reason}, author_id=user_id)
    if commit:
        db.session.commit()
    return sale


def refund_sale(sale, user_id, amount, method, motif, authorized_by_id=None, restock=True, commit=True):
    """Rembourse (total ou partiel) une vente validee.

    Le remboursement total passe la vente au statut `remboursee`.
    """
    if sale.status not in (SaleStatus.VALIDEE, SaleStatus.REMBOURSEE):
        raise ValueError("Cette vente ne peut pas etre remboursee.")

    amount = dec(amount)
    if amount <= 0:
        raise ValueError("Le montant rembourse doit etre positif.")

    refund = Refund(
        sale_id=sale.id,
        amount=amount,
        currency=sale.currency,
        method=method or PaymentMethod.ESPECE,
        motif=(motif or "").strip() or None,
        restock=bool(restock),
        authorized_by_id=authorized_by_id or user_id,
        user_id=user_id,
    )
    db.session.add(refund)

    if refund.restock:
        _reverse_stock(sale, user_id, f"Remboursement {sale.numero}", restock=True)
    _reverse_cash(sale, user_id, f"Remboursement {sale.numero}", amount=amount)

    total_refunded = sum((dec(r.amount) for r in sale.refunds), Decimal("0")) + amount
    if total_refunded >= dec(sale.montant_total):
        sale.status = SaleStatus.REMBOURSEE

    _queue_sync(
        "sale",
        "refund",
        sale.uuid,
        payload={"amount": str(amount), "motif": refund.motif},
        author_id=user_id,
    )
    if commit:
        db.session.commit()
    return refund
