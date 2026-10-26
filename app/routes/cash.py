"""Caisse : ouverture, mouvements, cloture et validation des sessions."""
from flask import Blueprint, abort, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required

from app.extensions import db
from app.models.sales import (
    CASH_IN_KINDS,
    CASH_MOVEMENT_LABELS,
    CASH_SESSION_STATUS_LABELS,
    CashMovement,
    CashMovementKind,
    CashSession,
    CashSessionStatus,
    Sale,
)
from app.models.user import get_setting
from app.security.audit import log_action
from app.security.decorators import permission_required
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
@permission_required(P.CASH_OPEN, mode="any")
def index():
    own = cash_service.find_open_session(vendeur_id=current_user.id)
    registers = cash_service.active_registers()

    query = CashSession.query
    if not _can_view_all():
        query = query.filter_by(vendeur_id=current_user.id)
    pager = paginate(query.order_by(CashSession.opened_at.desc()))

    return render_template(
        "cash/index.html",
        own_session=own,
        registers=registers,
        pager=pager,
        sessions=pager.items,
        labels=CASH_SESSION_STATUS_LABELS,
    )


@cash_bp.route("/ouvrir", methods=["POST"])
@login_required
@permission_required(P.CASH_OPEN)
def open_session():
    register = cash_service.get_register(request.form.get("register_id", type=int))
    solde = dec(request.form.get("solde_initial"))
    if register is None:
        flash("Selectionnez une caisse.", "danger")
        return redirect(url_for("cash.index"))
    if cash_service.find_open_session(vendeur_id=current_user.id):
        flash("Vous avez deja une caisse ouverte.", "warning")
        return redirect(url_for("cash.index"))

    try:
        session = cash_service.open_session(register, current_user.id, solde)
    except ValueError as exc:
        flash(str(exc), "danger")
        return redirect(url_for("cash.index"))

    log_action(
        "cash_open",
        entity="cash_session",
        entity_uuid=session.uuid,
        after={"register": register.name, "solde_initial": str(solde)},
        commit=True,
    )
    flash(f"Caisse « {register.name} » ouverte.", "success")
    return redirect(url_for("cash.session_detail", session_id=session.id))


@cash_bp.route("/<int:session_id>")
@login_required
@permission_required(P.CASH_OPEN, mode="any")
def session_detail(session_id):
    session = _load_session(session_id)
    theorique = session.compute_theorique()
    movements_pager = paginate(
        CashMovement.query.filter_by(session_id=session.id).order_by(CashMovement.created_at.desc()),
        key="mpage",
    )
    sales_pager = paginate(
        Sale.query.filter_by(cash_session_id=session.id).order_by(Sale.created_at.desc()),
        key="spage",
    )
    return render_template(
        "cash/session.html",
        session=session,
        theorique=theorique,
        movements=movements_pager.items,
        movements_pager=movements_pager,
        sales=sales_pager.items,
        sales_pager=sales_pager,
        labels=CASH_MOVEMENT_LABELS,
        statuses=CASH_SESSION_STATUS_LABELS,
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
    amount = dec(request.form.get("amount"))
    reason = (request.form.get("reason") or "").strip()
    if kind not in (CashMovementKind.APPORT, CashMovementKind.RETRAIT):
        flash("Type de mouvement non autorise ici.", "danger")
        return redirect(url_for("cash.session_detail", session_id=session.id))
    if amount <= 0:
        flash("Le montant doit etre positif.", "danger")
        return redirect(url_for("cash.session_detail", session_id=session.id))

    signed = amount if kind in CASH_IN_KINDS else -amount
    cash_service.record_cash(
        session, kind, signed, reason=reason or None, user_id=current_user.id
    )
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


@cash_bp.route("/<int:session_id>/fermer", methods=["POST"])
@login_required
@permission_required(P.CASH_CLOSE)
def close_session(session_id):
    session = _load_session(session_id)
    if not session.is_open:
        flash("Cette caisse n'est pas ouverte.", "warning")
        return redirect(url_for("cash.session_detail", session_id=session.id))

    solde_compte = dec(request.form.get("solde_compte"))
    motif = (request.form.get("motif_ecart") or "").strip()
    theorique = session.compute_theorique()
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
