"""Logique de vente : creation, validation, annulation, remboursement.

Une vente validee est **immuable** : on ne la modifie ni ne la supprime. Toute
correction passe par une contre-ecriture (annulation / remboursement) tracee.
"""
from datetime import date
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

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
from app.services import cash as cash_service
from app.services.stock import conversion_factor, dec, record_movement


class StockInsuffisant(ValueError):
    """Le stock disponible (valide) ne couvre pas la quantite demandee."""


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
    return dec(0)


def sellable_units(product, currency):
    """Unites de vente du produit dans la devise demandee."""
    return [
        pu for pu in product.selling_units
        if pu.active and pu.currency == currency
    ]


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
    if cash_session is None or not cash_session.is_open:
        raise ValueError("Ouvrez une caisse avant d'enregistrer une vente.")
    if not cash_session.register.active:
        raise ValueError("La caisse sélectionnée est inactive.")
    if currency != cash_session.currency:
        raise ValueError("La devise de la vente doit correspondre à celle de la caisse.")

    if not items:
        raise ValueError("Le panier est vide.")

    def decimal_value(value, label):
        try:
            result = Decimal(str(value).strip().replace(",", "."))
        except (InvalidOperation, TypeError, ValueError):
            raise ValueError(f"{label} doit etre un nombre valide.") from None
        if not result.is_finite():
            raise ValueError(f"{label} doit etre un nombre valide.")
        return result

    requested_stock = {}
    subtotal = Decimal("0")
    for item in items:
        product = item.get("product")
        unit_id = item.get("unit_id")
        quantity = decimal_value(item.get("quantity"), "La quantité")
        if product is None or not product.active:
            raise ValueError("Un produit du panier est introuvable ou inactif.")
        if quantity <= 0:
            raise ValueError(f"La quantité demandée pour {product.name} doit être positive.")
        if unit_id not in {pu.unit_id for pu in sellable_units(product, currency)}:
            raise ValueError(
                f"Le format de vente selectionne pour {product.name} n'est plus disponible."
            )
        factor = conversion_factor(product, unit_id)
        requested_stock[product.id] = requested_stock.get(product.id, Decimal("0")) + quantity * factor
        price = unit_price(product, unit_id, currency)
        if price <= 0:
            raise ValueError(f"Aucun prix de vente valide n'est défini pour {product.name}.")
        subtotal += (quantity * price).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

    subtotal = subtotal.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    discount = decimal_value(remise, "La remise").quantize(
        Decimal("0.01"), rounding=ROUND_HALF_UP
    )
    if discount < 0:
        raise ValueError("La remise ne peut pas être négative.")
    if discount > subtotal:
        raise ValueError("La remise ne peut pas dépasser le sous-total.")
    total = subtotal - discount
    valid_payment_methods = {PaymentMethod.ESPECE, PaymentMethod.BANQUE}
    payment_total = Decimal("0")
    normalized_payments = []
    for pay in payments or []:
        if not isinstance(pay, dict):
            raise ValueError("Un moyen de paiement est invalide.")
        amount = decimal_value(pay.get("amount"), "Le montant payé").quantize(
            Decimal("0.01"), rounding=ROUND_HALF_UP
        )
        method = pay.get("method") or PaymentMethod.ESPECE
        if amount <= 0:
            raise ValueError("Chaque paiement doit avoir un montant positif.")
        if method not in valid_payment_methods:
            raise ValueError("Le moyen de paiement sélectionné n'est pas valide.")
        payment_total += amount
        normalized_payments.append((pay, amount, method))
    if payment_total > total:
        raise ValueError("Le montant payé ne peut pas dépasser le total de la vente.")

    for item in items:
        product = item["product"]
        disponible = dec(product.stock_qty)
        demande = requested_stock[product.id]
        if disponible < demande:
            raise StockInsuffisant(
                f"Stock insuffisant pour {product.name} : "
                f"{disponible} {product.base_unit.label if product.base_unit else ''} "
                f"disponibles, {demande} demandés. "
                f"Validez une entrée de stock avant de vendre ce produit."
            )

    sale = Sale(
        numero=next_sale_number(),
        vendeur_id=vendeur_id,
        cash_session_id=cash_session.id if cash_session else None,
        currency=currency,
        status=SaleStatus.VALIDEE,
        remise=discount,
        notes=(notes or "").strip() or None,
    )
    db.session.add(sale)
    db.session.flush()

    for item in items:
        product = item["product"]
        unit_id = item.get("unit_id")
        quantity = Decimal(str(item.get("quantity")).strip().replace(",", "."))

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

    sale.montant_total = total

    for pay, amount, method in normalized_payments:
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

    sale.montant_paye = payment_total
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

    if commit:
        db.session.commit()
    return refund
