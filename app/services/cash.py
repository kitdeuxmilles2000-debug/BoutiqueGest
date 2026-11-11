"""Logique de caisse : ouverture, mouvements, cloture et validation."""
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

from sqlalchemy import case

from app.extensions import db
from app.models.base import utcnow
from app.models.sales import (
    CASH_IN_KINDS,
    CASH_MOVEMENT_LABELS,
    CashMovement,
    CashMovementKind,
    CashRegister,
    CashSession,
    CashSessionStatus,
)
from app.services.stock import dec

MANUAL_MOVEMENT_KINDS = (
    CashMovementKind.APPORT,
    CashMovementKind.RETRAIT,
    CashMovementKind.AJUSTEMENT,
)


def is_manual_movement(movement):
    """Mouvement corrigeable directement (sans contre-passation)."""
    return (
        movement.source_type in (None, "", "manual")
        and movement.kind in MANUAL_MOVEMENT_KINDS
    )


def _insufficient_balance(session, available, requested):
    return ValueError(
        "Operation refusee : le solde disponible de la caisse "
        f"({money_value(available)} {session.currency}) est insuffisant pour "
        f"retirer {money_value(requested)} {session.currency}. "
        "Le solde d'une caisse ne peut jamais devenir negatif."
    )


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
    """Enregistre un mouvement de caisse. `amount` est signe (+ entree / - sortie).

    Une sortie ne peut jamais rendre le solde theorique negatif : la caisse ne
    peut pas distribuer un montant qui n'existe pas.
    """
    amount = money_value(amount)
    if amount == 0:
        raise ValueError("Le montant du mouvement doit etre different de zero.")
    if currency and currency != session.currency:
        raise ValueError("La devise du mouvement doit correspondre a celle de la caisse.")
    if amount < 0:
        available = theorique_for(session)
        if available + amount < 0:
            raise _insufficient_balance(session, available, -amount)
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


def theorique_for(session):
    """Calcule le solde theorique en une seule requete (evite de charger tous les mouvements)."""
    total = (
        db.session.query(db.func.coalesce(db.func.sum(CashMovement.amount), 0))
        .filter(CashMovement.session_id == session.id)
        .scalar()
    )
    return dec(session.solde_initial) + dec(total)


def summary_for(session):
    """Totaux d'une session : fond, entrees, sorties, solde et nombre d'operations."""
    rows = (
        db.session.query(
            db.func.coalesce(
                db.func.sum(case((CashMovement.amount > 0, CashMovement.amount), else_=0)),
                0,
            ),
            db.func.coalesce(
                db.func.sum(case((CashMovement.amount < 0, -CashMovement.amount), else_=0)),
                0,
            ),
            db.func.count(CashMovement.id),
        )
        .filter(CashMovement.session_id == session.id)
        .one()
    )
    entrees = dec(rows[0])
    sorties = dec(rows[1])
    solde = dec(session.solde_initial) + entrees - sorties
    return {
        "solde_initial": dec(session.solde_initial),
        "entrees": entrees,
        "sorties": sorties,
        "solde": solde,
        "operations": int(rows[2] or 0),
    }


def recalculate_session(session, commit=True):
    """Recalcule le solde theorique et l'ecart apres une correction."""
    theorique = theorique_for(session)
    session.solde_theorique = theorique
    if session.solde_compte is not None:
        session.ecart = dec(session.solde_compte) - theorique
    if commit:
        db.session.commit()
    return theorique


def correct_manual_movement(movement, *, amount, kind, reason=None, user_id=None, commit=True):
    """Corrige un apport/retrait saisi manuellement, sans jamais rendre le solde negatif."""
    if not is_manual_movement(movement):
        raise ValueError(
            "Ce mouvement est lie a une vente, une depense ou un reglement : "
            "utilisez une contre-passation securisee."
        )
    if kind not in (CashMovementKind.APPORT, CashMovementKind.RETRAIT):
        raise ValueError("Le type corrige doit etre un apport ou un retrait.")
    montant = money_value(amount)
    if montant <= 0:
        raise ValueError("Le montant doit etre positif.")
    signed = montant if kind == CashMovementKind.APPORT else -montant

    session = movement.session
    balance_without = theorique_for(session) - dec(movement.amount)
    if balance_without + signed < 0:
        raise _insufficient_balance(session, balance_without, montant)

    movement.kind = kind
    movement.amount = signed
    movement.reason = (reason or "").strip() or movement.reason
    movement.user_id = user_id or movement.user_id
    recalculate_session(session, commit=False)
    if commit:
        db.session.commit()
    return movement


def delete_manual_movement(movement, *, user_id=None, commit=True):
    """Supprime un mouvement manuel si le solde reste positif."""
    if not is_manual_movement(movement):
        raise ValueError(
            "Ce mouvement est lie a une vente, une depense ou un reglement : "
            "utilisez une contre-passation securisee."
        )
    session = movement.session
    balance_after = theorique_for(session) - dec(movement.amount)
    if balance_after < 0:
        raise ValueError(
            "Suppression impossible : cette operation est necessaire pour "
            f"maintenir un solde positif ({money_value(balance_after)} {session.currency})."
        )
    db.session.delete(movement)
    recalculate_session(session, commit=False)
    if commit:
        db.session.commit()
    return True


def reverse_movement(movement, *, reason=None, user_id=None, commit=True):
    """Contre-passe un mouvement lie (vente, depense, reglement) par une ecriture inverse."""
    session = movement.session
    existing = CashMovement.query.filter_by(
        session_id=session.id,
        source_type="correction",
        source_uuid=movement.uuid,
    ).first()
    if existing is not None:
        raise ValueError("Ce mouvement a deja ete contre-passe.")
    montant = -dec(movement.amount)
    if montant == 0:
        raise ValueError("Ce mouvement est deja nul.")
    reversal = record_cash(
        session,
        CashMovementKind.AJUSTEMENT,
        montant,
        source_type="correction",
        source_uuid=movement.uuid,
        reason=(reason or "").strip()
        or f"Contre-passation {CASH_MOVEMENT_LABELS.get(movement.kind, movement.kind)}",
        user_id=user_id,
        commit=False,
    )
    recalculate_session(session, commit=False)
    if commit:
        db.session.commit()
    return reversal


def close_session(session, solde_compte, motif=None, commit=True):
    if not session.is_open:
        raise ValueError("Cette caisse n'est pas ouverte.")
    session.solde_theorique = theorique_for(session)
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
