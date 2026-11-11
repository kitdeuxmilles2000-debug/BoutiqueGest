"""Caisse : ouverture, mouvements, cloture et validation des sessions."""
from flask import Blueprint, abort, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import joinedload

from app.extensions import db
from app.models.sales import (
    CASH_IN_KINDS,
    CASH_MOVEMENT_LABELS,
    CASH_SESSION_STATUS_LABELS,
    CashMovement,
    CashMovementKind,
    CashRegister,
    CashSession,
    CashSessionStatus,
    Sale,
)
from app.models.user import get_setting
from app.security.audit import log_action
from app.security.decorators import admin_password_required, permission_required
from app.security.permissions import P
from app.services import cash as cash_service
from app.services import settings as settings_service
from app.services.pagination import paginate
from app.services.stock import dec

cash_bp = Blueprint("cash", __name__, url_prefix="/caisse")


def _can_view_all():
    return current_user.has_permission(P.CASH_VIEW_ALL)


def _load_session(session_id):
    session = db.session.get(CashSession, session_id) or abort(404)
    if session.vendeur_id != current_user.id and not _can_view_all():
        abort(403)
    return session


@cash_bp.route("/")
@login_required
@permission_required(P.CASH_OPEN, P.CASH_VIEW_ALL, mode="any")
def index():
    # Ne semer les caisses par defaut qu'une seule fois : evite une ecriture
    # (et un commit) a chaque affichage de la page Caisse.
    registers = cash_service.active_registers()
    if not registers and CashRegister.query.count() == 0:
        from app.services.seed import seed_registers

        seed_registers()
        registers = cash_service.active_registers()

    own = cash_service.find_open_session(vendeur_id=current_user.id)

    query = CashSession.query.options(
        joinedload(CashSession.register),
        joinedload(CashSession.vendeur),
    )
    if not _can_view_all():
        query = query.filter_by(vendeur_id=current_user.id)
    pager = paginate(query.order_by(CashSession.opened_at.desc()))

    # Solde theorique des sessions affichees : une seule requete agregee
    # au lieu de charger tous les mouvements session par session (N+1).
    session_ids = [s.id for s in pager.items]
    totals = {}
    if session_ids:
        totals = dict(
            db.session.query(
                CashMovement.session_id,
                db.func.coalesce(db.func.sum(CashMovement.amount), 0),
            )
            .filter(CashMovement.session_id.in_(session_ids))
            .group_by(CashMovement.session_id)
            .all()
        )
    for session in pager.items:
        session.display_theorique = dec(session.solde_initial) + dec(totals.get(session.id, 0))

    own_summary = cash_service.summary_for(own) if own is not None else None

    open_query = CashSession.query.filter_by(status=CashSessionStatus.OUVERTE)
    if not _can_view_all():
        open_query = open_query.filter_by(vendeur_id=current_user.id)
    open_sessions = open_query.all()
    open_ids = [s.id for s in open_sessions]
    open_movements = {}
    if open_ids:
        open_movements = dict(
            db.session.query(
                CashMovement.session_id,
                db.func.coalesce(db.func.sum(CashMovement.amount), 0),
            )
            .filter(CashMovement.session_id.in_(open_ids))
            .group_by(CashMovement.session_id)
            .all()
        )
    open_totals = {}
    for s in open_sessions:
        amount = dec(s.solde_initial) + dec(open_movements.get(s.id, 0))
        s.display_theorique = amount
        open_totals[s.currency] = open_totals.get(s.currency, dec(0)) + amount

    rate = settings_service.latest_rate()

    return render_template(
        "cash/index.html",
        own_session=own,
        own_summary=own_summary,
        registers=registers,
        pager=pager,
        sessions=pager.items,
        labels=CASH_SESSION_STATUS_LABELS,
        open_sessions=open_sessions,
        open_totals=open_totals,
        rate=rate,
    )


@cash_bp.route("/ouvrir", methods=["POST"])
@login_required
@permission_required(P.CASH_OPEN)
def open_session():
    register = cash_service.get_register(request.form.get("register_id", type=int))
    try:
        solde = cash_service.money_value(request.form.get("solde_initial") or "0", "Le fond initial")
    except ValueError as exc:
        flash(str(exc), "danger")
        return redirect(url_for("cash.index"))
    if register is None:
        flash("Selectionnez une caisse.", "danger")
        return redirect(url_for("cash.index"))
    if not register.active:
        flash("Cette caisse est inactive et ne peut pas etre ouverte.", "danger")
        return redirect(url_for("cash.index"))
    if solde < 0:
        flash("Le fond initial ne peut pas etre negatif.", "danger")
        return redirect(url_for("cash.index"))
    if cash_service.find_open_session(vendeur_id=current_user.id):
        flash("Vous avez deja une caisse ouverte.", "warning")
        return redirect(url_for("pos.index") if request.form.get("next") == "pos" else url_for("cash.index"))

    try:
        session = cash_service.open_session(register, current_user.id, solde)
    except ValueError as exc:
        flash(str(exc), "danger")
        return redirect(url_for("cash.index"))
    except IntegrityError:
        db.session.rollback()
        flash("Cette caisse vient d'etre ouverte par un autre utilisateur. Choisissez une caisse disponible.", "warning")
        return redirect(url_for("cash.index"))

    log_action(
        "cash_open",
        entity="cash_session",
        entity_uuid=session.uuid,
        after={"register": register.name, "solde_initial": str(solde)},
        commit=True,
    )
    flash(f"Caisse « {register.name} » ouverte.", "success")
    if request.form.get("next") == "pos" and current_user.has_permission(P.SALES_CREATE):
        return redirect(url_for("pos.index"))
    return redirect(url_for("cash.session_detail", session_id=session.id))


@cash_bp.route("/<int:session_id>")
@login_required
@permission_required(P.CASH_OPEN, P.CASH_VIEW_ALL, mode="any")
def session_detail(session_id):
    session = _load_session(session_id)
    theorique = cash_service.theorique_for(session)
    summary = cash_service.summary_for(session)
    movements_pager = paginate(
        CashMovement.query.filter_by(session_id=session.id).order_by(CashMovement.created_at.desc()),
        key="mpage",
    )
    movement_uuids = [m.uuid for m in movements_pager.items if m.uuid]
    reversed_uuids = set()
    if movement_uuids:
        reversed_uuids = {
            row[0]
            for row in db.session.query(CashMovement.source_uuid)
            .filter(
                CashMovement.session_id == session.id,
                CashMovement.source_type == "correction",
                CashMovement.source_uuid.in_(movement_uuids),
            )
            .all()
        }
    for movement in movements_pager.items:
        movement.is_manual = cash_service.is_manual_movement(movement)
        movement.is_reversed = movement.uuid in reversed_uuids
    sales_pager = paginate(
        Sale.query.filter_by(cash_session_id=session.id).order_by(Sale.created_at.desc()),
        key="spage",
    )
    rate = settings_service.latest_rate()
    return render_template(
        "cash/session.html",
        session=session,
        theorique=theorique,
        summary=summary,
        movements=movements_pager.items,
        movements_pager=movements_pager,
        sales=sales_pager.items,
        sales_pager=sales_pager,
        labels=CASH_MOVEMENT_LABELS,
        statuses=CASH_SESSION_STATUS_LABELS,
        can_correct=current_user.has_permission(P.CASH_OPEN)
        or current_user.has_permission(P.CASH_VIEW_ALL),
        rate=rate,
    )


@cash_bp.route("/<int:session_id>/mouvement", methods=["POST"])
@login_required
@permission_required(P.CASH_OPEN)
def add_movement(session_id):
    session = _load_session(session_id)
    if not session.is_open:
        flash("La caisse est cloturee.", "danger")
        return redirect(url_for("cash.session_detail", session_id=session.id))

    kind = request.form.get("kind") or CashMovementKind.APPORT
    try:
        amount = cash_service.money_value(request.form.get("amount"), "Le montant")
    except ValueError as exc:
        flash(str(exc), "danger")
        return redirect(url_for("cash.session_detail", session_id=session.id))
    reason = (request.form.get("reason") or "").strip()
    if kind not in (CashMovementKind.APPORT, CashMovementKind.RETRAIT):
        flash("Type de mouvement non autorise ici.", "danger")
        return redirect(url_for("cash.session_detail", session_id=session.id))
    if amount <= 0:
        flash("Le montant doit etre positif.", "danger")
        return redirect(url_for("cash.session_detail", session_id=session.id))

    signed = amount if kind in CASH_IN_KINDS else -amount
    try:
        cash_service.record_cash(
            session, kind, signed, reason=reason or None, user_id=current_user.id
        )
    except ValueError as exc:
        db.session.rollback()
        flash(str(exc), "danger")
        return redirect(url_for("cash.session_detail", session_id=session.id))
    log_action(
        "cash_movement",
        entity="cash_session",
        entity_uuid=session.uuid,
        after={"kind": kind, "amount": str(signed)},
        reason=reason,
        commit=True,
    )
    flash("Mouvement de caisse enregistre.", "success")
    return redirect(url_for("cash.session_detail", session_id=session.id))


@cash_bp.route("/<int:session_id>/mouvement/<int:movement_id>/corriger", methods=["POST"])
@login_required
@permission_required(P.CASH_OPEN, P.CASH_VIEW_ALL, mode="any")
@admin_password_required()
def movement_correct(session_id, movement_id):
    session = _load_session(session_id)
    movement = db.session.get(CashMovement, movement_id) or abort(404)
    if movement.session_id != session.id:
        abort(404)

    reason = (request.form.get("reason") or "").strip()
    before = {
        "kind": movement.kind,
        "amount": str(movement.amount),
        "reason": movement.reason,
        "source_type": movement.source_type,
    }
    try:
        if cash_service.is_manual_movement(movement):
            cash_service.correct_manual_movement(
                movement,
                amount=request.form.get("amount"),
                kind=request.form.get("kind") or movement.kind,
                reason=reason,
                user_id=current_user.id,
            )
            action = "cash_movement_correct"
            message = "Mouvement de caisse corrige."
        else:
            cash_service.reverse_movement(
                movement,
                reason=reason,
                user_id=current_user.id,
            )
            action = "cash_movement_reverse"
            message = (
                "Contre-passation enregistree : le mouvement d'origine reste "
                "trace et le solde de caisse est reequilibre."
            )
    except ValueError as exc:
        db.session.rollback()
        flash(str(exc), "danger")
        return redirect(url_for("cash.session_detail", session_id=session.id))

    log_action(
        action,
        entity="cash_session",
        entity_uuid=session.uuid,
        before=before,
        after={"solde": str(cash_service.theorique_for(session))},
        reason=reason,
        commit=True,
    )
    flash(message, "success")
    return redirect(url_for("cash.session_detail", session_id=session.id))


@cash_bp.route("/<int:session_id>/mouvement/<int:movement_id>/supprimer", methods=["POST"])
@login_required
@permission_required(P.CASH_OPEN, P.CASH_VIEW_ALL, mode="any")
@admin_password_required()
def movement_delete(session_id, movement_id):
    session = _load_session(session_id)
    movement = db.session.get(CashMovement, movement_id) or abort(404)
    if movement.session_id != session.id:
        abort(404)

    reason = (request.form.get("reason") or "").strip()
    before = {
        "kind": movement.kind,
        "amount": str(movement.amount),
        "reason": movement.reason,
        "source_type": movement.source_type,
    }
    try:
        if cash_service.is_manual_movement(movement):
            cash_service.delete_manual_movement(
                movement, user_id=current_user.id
            )
            action = "cash_movement_delete"
            message = "Mouvement de caisse supprime et solde recalcule."
        else:
            cash_service.reverse_movement(
                movement,
                reason=reason,
                user_id=current_user.id,
            )
            action = "cash_movement_reverse"
            message = (
                "Mouvement lie : une contre-passation a ete enregistree pour "
                "reequilibrer la caisse."
            )
    except ValueError as exc:
        db.session.rollback()
        flash(str(exc), "danger")
        return redirect(url_for("cash.session_detail", session_id=session.id))

    log_action(
        action,
        entity="cash_session",
        entity_uuid=session.uuid,
        before=before,
        after={"solde": str(cash_service.theorique_for(session))},
        reason=reason,
        commit=True,
    )
    flash(message, "success")
    return redirect(url_for("cash.session_detail", session_id=session.id))


@cash_bp.route("/<int:session_id>/recalculer", methods=["POST"])
@login_required
@permission_required(P.CASH_OPEN, P.CASH_VIEW_ALL, mode="any")
def recalculate(session_id):
    session = _load_session(session_id)
    theorique = cash_service.recalculate_session(session)
    log_action(
        "cash_recalculate",
        entity="cash_session",
        entity_uuid=session.uuid,
        after={"theorique": str(theorique)},
        commit=True,
    )
    flash("Solde de caisse recalcule.", "success")
    return redirect(url_for("cash.session_detail", session_id=session.id))


@cash_bp.route("/<int:session_id>/fermer", methods=["POST"])
@login_required
@permission_required(P.CASH_CLOSE)
def close_session(session_id):
    session = _load_session(session_id)
    if not session.is_open:
        flash("Cette caisse n'est pas ouverte.", "warning")
        return redirect(url_for("cash.session_detail", session_id=session.id))

    try:
        solde_compte = cash_service.money_value(request.form.get("solde_compte"), "Le montant compte")
    except ValueError as exc:
        flash(str(exc), "danger")
        return redirect(url_for("cash.session_detail", session_id=session.id))
    motif = (request.form.get("motif_ecart") or "").strip()
    theorique = cash_service.theorique_for(session)
    ecart = solde_compte - theorique
    if ecart != 0 and not motif:
        flash("Un ecart de caisse doit etre explique (motif obligatoire).", "danger")
        return redirect(url_for("cash.session_detail", session_id=session.id))

    cash_service.close_session(session, solde_compte, motif)
    log_action(
        "cash_close",
        entity="cash_session",
        entity_uuid=session.uuid,
        after={"theorique": str(theorique), "compte": str(solde_compte), "ecart": str(ecart)},
        reason=motif,
        commit=True,
    )
    flash("Cloture soumise. En attente de validation.", "success")
    return redirect(url_for("cash.session_detail", session_id=session.id))


@cash_bp.route("/<int:session_id>/valider", methods=["POST"])
@login_required
@permission_required(P.CASH_VALIDATE)
def validate_session(session_id):
    session = db.session.get(CashSession, session_id) or abort(404)
    if session.status == CashSessionStatus.VALIDEE:
        flash("Cette cloture est deja validee.", "warning")
        return redirect(url_for("cash.session_detail", session_id=session.id))
    if session.status != CashSessionStatus.SOUMISE:
        flash("La cloture doit d'abord etre soumise.", "danger")
        return redirect(url_for("cash.session_detail", session_id=session.id))

    cash_service.validate_session(session, current_user.id)
    log_action(
        "cash_validate",
        entity="cash_session",
        entity_uuid=session.uuid,
        after={"ecart": str(session.ecart)},
        commit=False,
    )
    db.session.commit()
    flash("Cloture validee.", "success")

    # Rapport journalier : mise en file apres cloture validee (envoi si SMTP configure
    # et si l'envoi immediat est active dans Administration > E-mails).
    report_to = get_setting(settings_service.REPORT_TO_SETTING, "")
    auto_send = get_setting(settings_service.REPORT_AUTO_SEND_SETTING, "0") == "1"
    if report_to:
        try:
            settings_service.queue_daily_report(report_to, user_id=current_user.id)
            flash(
                "Rapport journalier mis en file d'attente (Administration > E-mails).",
                "success",
            )
            if auto_send and settings_service.smtp_configured():
                sent, errors = settings_service.send_pending()
                if errors:
                    flash(
                        "Rapport prepare mais non envoye : verifiez la configuration SMTP.",
                        "warning",
                    )
                else:
                    flash(f"Rapport envoye a {report_to}.", "success")
        except Exception:  # noqa: BLE001 - ne jamais bloquer la cloture
            db.session.rollback()
            flash(
                "La cloture est validee, mais le rapport n'a pas pu etre prepare. "
                "Verifiez la configuration e-mail.",
                "warning",
            )

    return redirect(url_for("cash.session_detail", session_id=session.id))
