"""Logique de caisse : ouverture, mouvements, cloture et validation."""
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

from app.extensions import db
from app.models.base import utcnow
from app.models.sales import (
    CASH_IN_KINDS,
    CashMovement,
    CashMovementKind,
    CashRegister,
    CashSession,
    CashSessionStatus,
)
from app.services.stock import dec


def money_value(value, label="Le montant"):
    """Parse a finite cash amount and round it to currency precision."""
    try:
        amount = Decimal(str(value).strip().replace(",", "."))
    except (InvalidOperation, TypeError, ValueError):
        raise ValueError(f"{label} doit etre un nombre valide.") from None
    if not amount.is_finite():
        raise ValueError(f"{label} doit etre un nombre valide.")
    return amount.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def sign_for(kind):
    """Signe d'un mouvement de caisse (+ entree / - sortie)."""
    return Decimal("1") if kind in CASH_IN_KINDS else Decimal("-1")


def active_registers():
    return CashRegister.query.filter_by(active=True).order_by(CashRegister.name).all()


def get_register(register_id):
    return db.session.get(CashRegister, register_id) if register_id else None


def open_session(register, vendeur_id, solde_initial=0, commit=True):
    if register is None or not register.active:
        raise ValueError("Selectionnez une caisse active.")
    opening_balance = money_value(solde_initial, "Le fond initial")
    if opening_balance < 0:
        raise ValueError("Le fond initial ne peut pas etre negatif.")
    existing = (
        CashSession.query.filter_by(register_id=register.id, status=CashSessionStatus.OUVERTE)
        .first()
    )
    if existing is not None:
        raise ValueError("Cette caisse est deja ouverte.")

    session = CashSession(
        register_id=register.id,
        vendeur_id=vendeur_id,
        currency=register.currency,
        solde_initial=opening_balance,
        status=CashSessionStatus.OUVERTE,
    )
    db.session.add(session)
    if commit:
        db.session.commit()
    return session


def find_open_session(vendeur_id=None, register_id=None):
    query = CashSession.query.filter_by(status=CashSessionStatus.OUVERTE)
    if vendeur_id is not None:
        query = query.filter_by(vendeur_id=vendeur_id)
    if register_id is not None:
        query = query.filter_by(register_id=register_id)
    return query.order_by(CashSession.opened_at.desc()).first()


def record_cash(
    session,
    kind,
    amount,
    *,
    currency=None,
    source_type=None,
    source_uuid=None,
    reason=None,
    user_id=None,
    commit=True,
):
    """Enregistre un mouvement de caisse. `amount` est signe (+ entree / - sortie)."""
    amount = money_value(amount)
    if amount == 0:
        raise ValueError("Le montant du mouvement doit etre different de zero.")
    if currency and currency != session.currency:
        raise ValueError("La devise du mouvement doit correspondre a celle de la caisse.")
    movement = CashMovement(
        session_id=session.id,
        kind=kind,
        amount=dec(amount),
        currency=currency or session.currency,
        source_type=source_type,
        source_uuid=source_uuid,
        reason=reason,
        user_id=user_id,
    )
    db.session.add(movement)
    if commit:
        db.session.commit()
    return movement


def close_session(session, solde_compte, motif=None, commit=True):
    if not session.is_open:
        raise ValueError("Cette caisse n'est pas ouverte.")
    session.solde_theorique = session.compute_theorique()
    session.solde_compte = money_value(solde_compte, "Le montant compte")
    if session.solde_compte < 0:
        raise ValueError("Le montant compte ne peut pas etre negatif.")
    session.ecart = session.solde_compte - session.solde_theorique
    session.motif_ecart = (motif or "").strip() or None
    session.status = CashSessionStatus.SOUMISE
    session.closed_at = utcnow()
    if commit:
        db.session.commit()
    return session


def validate_session(session, user_id, commit=True):
    session.status = CashSessionStatus.VALIDEE
    session.validated_by_id = user_id
    session.validated_at = utcnow()
    if commit:
        db.session.commit()
    return session
