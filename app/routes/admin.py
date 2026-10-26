"""Administration : utilisateurs, roles, audit, sauvegardes, sync, taux, e-mails."""
import os
from datetime import datetime

from flask import (
    Blueprint,
    Response,
    current_app,
    flash,
    redirect,
    render_template,
    request,
    send_file,
    url_for,
)
from flask_login import current_user, login_required

from app.extensions import db
from app.models.audit import AuditLog
from app.models.settings import OUTBOX_STATUS_LABELS, OutboxMessage
from app.models.user import Role, User, get_setting, set_setting
from app.security.audit import log_action
from app.security.decorators import (
    admin_password_required,
    owner_only,
    owner_reauth_required,
    permission_required,
)
from app.security.permissions import P
from app.services import backup as backup_service
from app.services import db_history as db_history_service
from app.services import reset as reset_service
from app.services import settings as settings_service
from app.services import sync as sync_service
from app.services.pagination import paginate
from app.services.reports import PERIODE_LABELS

admin_bp = Blueprint("admin", __name__, url_prefix="/admin")


@admin_bp.route("/users")
@login_required
@permission_required(P.USERS_VIEW)
def users():
    pager = paginate(User.query.order_by(User.username))
    return render_template("admin/users.html", users=pager.items, pager=pager)


@admin_bp.route("/users/new", methods=["GET", "POST"])
@login_required
@permission_required(P.USERS_MANAGE)
def user_new():
    roles = Role.query.order_by(Role.label).all()

    if request.method == "POST":
        username = request.form.get("username", "").strip()
        full_name = request.form.get("full_name", "").strip()
        password = request.form.get("password", "")
        role_id = request.form.get("role_id") or None

        errors = []
        if not username:
            errors.append("Le nom d'utilisateur est obligatoire.")
        if not full_name:
            errors.append("Le nom complet est obligatoire.")
        if len(password) < 8:
            errors.append("Le mot de passe doit contenir au moins 8 caracteres.")
        if User.query.filter_by(username=username).first():
            errors.append("Ce nom d'utilisateur existe deja.")

        if errors:
            for message in errors:
                flash(message, "danger")
        else:
            user = User(username=username, full_name=full_name, active=True)
            user.set_password(password)
            if role_id:
                user.role_id = int(role_id)
            db.session.add(user)
            db.session.flush()
            log_action(
                "user_create",
                entity="user",
                entity_uuid=user.uuid,
                after={"username": username, "role_id": role_id},
                commit=True,
            )
            flash(f"Utilisateur « {username} » cree.", "success")
            return redirect(url_for("admin.users"))

    return render_template("admin/user_form.html", roles=roles)


@admin_bp.route("/roles")
@login_required
@permission_required(P.ROLES_MANAGE)
def roles():
    all_roles = Role.query.order_by(Role.name).all()
    return render_template("admin/roles.html", roles=all_roles)


@admin_bp.route("/audit")
@login_required
@permission_required(P.AUDIT_VIEW)
def audit():
    page = request.args.get("page", 1, type=int)
    pagination = (
        AuditLog.query.order_by(AuditLog.at.desc())
        .paginate(page=page, per_page=50, error_out=False)
    )
    return render_template("admin/audit.html", pagination=pagination)


@admin_bp.route("/sauvegardes")
@login_required
@permission_required(P.BACKUP_MANAGE)
def backups():
    try:
        db_history_service.create_snapshot(label="snapshot")
    except Exception:
        pass
    return render_template(
        "admin/backups.html",
        backups=backup_service.list_backups(),
        retention=int(request.args.get("retention", 0)) or None,
        snapshots=db_history_service.list_snapshots(),
    )


@admin_bp.route("/sauvegardes/creer", methods=["POST"])
@login_required
@permission_required(P.BACKUP_MANAGE)
def backup_create():
    try:
        meta = backup_service.create_backup(label="manuel")
    except RuntimeError as exc:
        flash(str(exc), "danger")
        return redirect(url_for("admin.backups"))

    log_action(
        "backup_create",
        entity="backup",
        after={"filename": meta["filename"], "size": meta["size"], "valid": meta["valid"]},
        commit=True,
    )
    if meta["valid"]:
        flash(f"Sauvegarde « {meta['filename']} » creee et verifiee (integrite OK).", "success")
    else:
        flash(f"Sauvegarde « {meta['filename']} » creee mais le controle d'integrite a echoue.", "danger")
    return redirect(url_for("admin.backups"))


@admin_bp.route("/sauvegardes/<filename>/telecharger")
@login_required
@permission_required(P.BACKUP_MANAGE)
def backup_download(filename):
    path = os.path.join(backup_service.backup_dir(), filename)
    if not os.path.exists(path):
        flash("Sauvegarde introuvable.", "danger")
        return redirect(url_for("admin.backups"))
    return send_file(path, as_attachment=True, download_name=filename)


@admin_bp.route("/sauvegardes/purger", methods=["POST"])
@login_required
@permission_required(P.BACKUP_MANAGE)
def backup_purge():
    removed = backup_service.purge_old_backups()
    log_action("backup_purge", entity="backup", after={"removed": removed}, commit=True)
    flash(f"Retention appliquee : {removed} ancienne(s) sauvegarde(s) supprimee(s).", "success")
    return redirect(url_for("admin.backups"))


@admin_bp.route("/sauvegardes/historique/creer", methods=["POST"])
@login_required
@owner_reauth_required()
@owner_only()
def history_snapshot_create():
    try:
        meta = db_history_service.create_snapshot(label="manuel")
        log_action("db_snapshot_create", entity="db_history", after=meta, commit=True)
        flash(f"Instantané créé : {meta['filename']}", "success")
    except Exception as exc:
        db.session.rollback()
        flash(f"Erreur création instantané : {exc}", "danger")
    return redirect(url_for("admin.backups"))


@admin_bp.route("/sauvegardes/historique/creer-ajax", methods=["POST"])
@login_required
def history_snapshot_create_ajax():
    try:
        meta = db_history_service.create_snapshot(label="auto")
        log_action("db_snapshot_create_auto", entity="db_history", after=meta, commit=True)
        return {"ok": True, "filename": meta["filename"]}, 200
    except Exception as exc:
        db.session.rollback()
        return {"ok": False, "error": str(exc)}, 500


@admin_bp.route("/sauvegardes/historique/<filename>/restaurer", methods=["POST"])
@login_required
@owner_reauth_required()
@owner_only()
def history_restore(filename):
    reason = (request.form.get("reason") or "").strip()
    if not reason:
        flash("Un motif est obligatoire pour restaurer un point historique.", "danger")
        return redirect(url_for("admin.backups"))
    try:
        res = db_history_service.restore_snapshot(filename, reason=reason)
        log_action("db_snapshot_restore", entity="db_history", after=res, reason=reason, commit=True)
        flash(
            "Base restaurée depuis l’historique. Redémarrez l’application pour appliquer les changements.",
            "warning",
        )
    except Exception as exc:
        db.session.rollback()
        flash(f"Erreur restauration : {exc}", "danger")
    return redirect(url_for("admin.backups"))


@admin_bp.route("/sauvegardes/historique/<filename>/telecharger")
@login_required
@owner_only()
def history_download(filename):
    if "/" in filename or "\\" in filename or ".." in filename:
        flash("Nom de fichier invalide.", "danger")
        return redirect(url_for("admin.backups"))
    path = os.path.join(db_history_service.history_dir(), filename)
    if not os.path.exists(path):
        flash("Snapshot introuvable.", "danger")
        return redirect(url_for("admin.backups"))
    return send_file(path, as_attachment=True, download_name=filename)


@admin_bp.route("/synchronisation")
@login_required
@permission_required(P.SYNC_MANAGE)
def sync():
    return render_template("admin/sync.html", stats=sync_service.stats())


@admin_bp.route("/synchronisation/traiter", methods=["POST"])
@login_required
@permission_required(P.SYNC_MANAGE)
def sync_process():
    bilan = sync_service.process_queue()
    log_action("sync_process", entity="sync", after=bilan, commit=True)
    if bilan["traites"] == 0:
        flash("Aucun evenement a envoyer (file a jour ou sync distante non configuree).", "success")
    else:
        flash(
            f"Sync : {bilan['acquittes']} acquitte(s), {bilan['erreurs']} erreur(s).",
            "success" if bilan["erreurs"] == 0 else "danger",
        )
    return redirect(url_for("admin.sync"))


# ------------------------------------------------------------ Taux de change
@admin_bp.route("/taux", methods=["GET", "POST"])
@login_required
@permission_required(P.SETTINGS_MANAGE)
def exchange_rate():
    if request.method == "POST":
        try:
            rate = settings_service.set_rate(
                rate=request.form.get("rate", "").replace(",", "."),
                effective_date=_parse_date(request.form.get("effective_date")),
                source=request.form.get("source") or None,
                notes=request.form.get("notes") or None,
                user_id=current_user.id,
                commit=False,
            )
            db.session.commit()
            flash(
                f"Taux enregistre : 1 USD = {rate.rate} CDF (effet {rate.effective_date:%d/%m/%Y}).",
                "success",
            )
        except (ValueError, ArithmeticError) as exc:
            db.session.rollback()
            flash(f"Taux invalide : {exc}", "danger")
        return redirect(url_for("admin.exchange_rate"))

    latest = settings_service.latest_rate()
    return render_template(
        "admin/exchange_rate.html",
        latest=latest,
        history=settings_service.rate_history(),
    )


# ------------------------------------------------------------ Prix et marges
@admin_bp.route("/prix", methods=["GET", "POST"])
@login_required
@permission_required(P.SETTINGS_MANAGE)
def pricing():
    from decimal import Decimal, InvalidOperation

    from app.models.user import set_setting
    from app.services import pricing as pricing_service

    if request.method == "POST":
        raw = (request.form.get("marge_objectif_defaut") or "").strip().replace(",", ".")
        try:
            value = Decimal(raw)
        except (InvalidOperation, ValueError):
            value = None
        if value is None or not (0 <= value < 100):
            flash("L'objectif de marge doit être un nombre entre 0 et 99 %.", "danger")
        else:
            set_setting(pricing_service.TARGET_MARGIN_SETTING, str(value))
            db.session.commit()
            flash(f"Objectif de marge par défaut : {value} %.", "success")
        return redirect(url_for("admin.pricing"))

    return render_template(
        "admin/pricing.html",
        marge_objectif=pricing_service.default_target_margin(),
    )


# ------------------------------------------------ Reinitialisation de la base
@admin_bp.route("/reinitialiser", methods=["GET", "POST"])
@login_required
@permission_required(P.SETTINGS_MANAGE)
@admin_password_required()
def reset_database():
    include_catalog = bool(request.form.get("include_catalog"))
    include_partners = bool(request.form.get("include_partners"))

    if request.method == "POST":
        if not reset_service.magic_word_ok(request.form.get("magic_word")):
            log_action(
                "database_reset_refused",
                entity="database",
                reason="phrase magique incorrecte",
                commit=True,
            )
            flash(
                "Réinitialisation refusée : phrase magique incorrecte. "
                "Écrivez exactement « clovis est une fleur ».",
                "danger",
            )
            return redirect(url_for("admin.reset_database"))

        try:
            meta = backup_service.create_backup(label="avant_reinitialisation")
        except RuntimeError as exc:
            flash(f"Réinitialisation annulée : sauvegarde impossible ({exc}).", "danger")
            return redirect(url_for("admin.reset_database"))
        if not meta.get("valid"):
            flash("Réinitialisation annulée : la sauvegarde de sécurité est invalide.", "danger")
            return redirect(url_for("admin.reset_database"))

        summary = reset_service.reset_operations(
            include_catalog=include_catalog, include_partners=include_partners
        )
        log_action(
            "database_reset",
            entity="database",
            after={"sauvegarde": meta["filename"], "supprime": summary},
            reason=(request.form.get("reason") or "").strip() or None,
            commit=True,
        )
        flash(
            "Base réinitialisée : toutes les opérations ont été supprimées. "
            f"Sauvegarde de sécurité : {meta['filename']}.",
            "success",
        )
        return redirect(url_for("main.dashboard"))

    counts = reset_service.collect_counts(
        include_catalog=include_catalog, include_partners=include_partners
    )
    return render_template(
        "admin/reset.html",
        counts=counts,
        total=sum(counts.values()),
        include_catalog=include_catalog,
        include_partners=include_partners,
    )


def _parse_date(value):
    if not value:
        return None
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except ValueError:
        return None


# --------------------------------------------------------- E-mails (rapport)
@admin_bp.route("/emails")
@login_required
@permission_required(P.SETTINGS_MANAGE)
def outbox():
    smtp = settings_service.smtp_config()
    pager = paginate(OutboxMessage.query.order_by(OutboxMessage.created_at.desc()))
    return render_template(
        "admin/outbox.html",
        pager=pager,
        messages=pager.items,
        status_labels=OUTBOX_STATUS_LABELS,
        smtp=smtp,
        smtp_configured=bool(smtp["host"]),
        security_labels=settings_service.SECURITY_LABELS,
        report_to=get_setting(settings_service.REPORT_TO_SETTING, ""),
        auto_send=get_setting(settings_service.REPORT_AUTO_SEND_SETTING, "0") == "1",
        periode_labels=PERIODE_LABELS,
        default_periode=request.args.get("periode", "jour"),
    )


@admin_bp.route("/emails/config", methods=["POST"])
@login_required
@permission_required(P.SETTINGS_MANAGE)
def outbox_save_config():
    host = (request.form.get("smtp_host") or "").strip()
    port = (request.form.get("smtp_port") or "").strip()
    security = (request.form.get("smtp_security") or "starttls").strip()
    user = (request.form.get("smtp_user") or "").strip()
    password = request.form.get("smtp_password") or ""
    sender = (request.form.get("smtp_sender") or "").strip()
    report_to = (request.form.get("report_email_to") or "").strip()
    auto_send = bool(request.form.get("report_auto_send"))

    try:
        settings_service.save_smtp_config(
            host=host,
            port=port,
            security=security,
            user=user,
            password=password,
            sender=sender,
            report_to=report_to,
            auto_send=auto_send,
        )
    except ValueError as exc:
        db.session.rollback()
        flash(str(exc), "danger")
        return redirect(url_for("admin.outbox"))

    log_action(
        "email_config_update",
        entity="settings",
        after={
            "host": host,
            "port": port,
            "security": security,
            "user": user,
            "auto_send": auto_send,
            "report_to": report_to,
        },
        commit=False,
    )
    db.session.commit()
    flash("Configuration e-mail enregistrée.", "success")
    return redirect(url_for("admin.outbox"))


@admin_bp.route("/emails/test-connexion", methods=["POST"])
@login_required
@permission_required(P.SETTINGS_MANAGE)
def outbox_test_connection():
    ok, message = settings_service.verify_connection()
    log_action(
        "email_test_connection",
        entity="settings",
        after={"ok": ok, "host": settings_service.smtp_config()["host"]},
        commit=True,
    )
    flash(message, "success" if ok else "danger")
    return redirect(url_for("admin.outbox"))


@admin_bp.route("/emails/test", methods=["POST"])
@login_required
@permission_required(P.SETTINGS_MANAGE)
def outbox_test_email():
    to_address = (request.form.get("to_address") or "").strip()
    if not to_address:
        to_address = get_setting(settings_service.REPORT_TO_SETTING, "")
    if to_address:
        set_setting(settings_service.REPORT_TO_SETTING, to_address)
    ok, message = settings_service.send_test_email(to_address)
    log_action(
        "email_test",
        entity="outbox",
        after={"to": to_address, "ok": ok},
        commit=True,
    )
    flash(message, "success" if ok else "danger")
    return redirect(url_for("admin.outbox"))


@admin_bp.route("/emails/apercu")
@login_required
@permission_required(P.SETTINGS_MANAGE)
def outbox_preview():
    periode = request.args.get("periode", "jour")
    if periode not in PERIODE_LABELS:
        periode = "jour"
    return Response(settings_service.build_report_html(periode), mimetype="text/html")


@admin_bp.route("/emails/<int:message_id>/apercu")
@login_required
@permission_required(P.SETTINGS_MANAGE)
def outbox_message_preview(message_id):
    msg = db.session.get(OutboxMessage, message_id)
    if msg is None:
        flash("Message introuvable.", "danger")
        return redirect(url_for("admin.outbox"))
    if msg.body_html:
        return Response(msg.body_html, mimetype="text/html")
    return Response(
        f"<!doctype html><meta charset='utf-8'><pre style='white-space:pre-wrap;font-family:Consolas,monospace;padding:24px'>{msg.body}</pre>",
        mimetype="text/html",
    )


@admin_bp.route("/emails/rapport", methods=["POST"])
@login_required
@permission_required(P.SETTINGS_MANAGE)
def outbox_queue_report():
    to_address = (request.form.get("to_address") or "").strip()
    periode = request.form.get("periode", "jour")
    if periode not in PERIODE_LABELS:
        periode = "jour"
    send_now = bool(request.form.get("send_now"))
    if not to_address:
        flash("Renseignez l'adresse destinataire.", "danger")
        return redirect(url_for("admin.outbox"))

    set_setting(settings_service.REPORT_TO_SETTING, to_address)
    try:
        msg = settings_service.queue_daily_report(
            to_address,
            user_id=current_user.id,
            commit=False,
            periode=periode,
        )
    except Exception as exc:  # noqa: BLE001 - on remonte l'erreur reelle
        db.session.rollback()
        flash(f"Le rapport n'a pas pu être généré : {exc}", "danger")
        return redirect(url_for("admin.outbox"))

    log_action(
        "email_queue",
        entity="outbox",
        entity_uuid=msg.uuid,
        after={"to": to_address, "periode": periode, "send_now": send_now},
        commit=False,
    )
    db.session.commit()
    flash(
        f"Rapport ({PERIODE_LABELS.get(periode, periode)}) mis en file d'attente.",
        "success",
    )

    if send_now:
        sent, errors = settings_service.send_pending()
        log_action(
            "email_send",
            entity="outbox",
            after={"envoyes": sent, "erreurs": errors},
            commit=True,
        )
        flash(
            f"Envoi immédiat : {sent} envoyé(s), {errors} erreur(s).",
            "success" if errors == 0 else "danger",
        )
        if errors:
            flash(
                "Vérifiez la configuration SMTP et le message d'erreur dans la file d'envoi.",
                "warning",
            )
    return redirect(url_for("admin.outbox"))


@admin_bp.route("/emails/envoyer", methods=["POST"])
@login_required
@permission_required(P.SETTINGS_MANAGE)
def outbox_send():
    sent, errors = settings_service.send_pending()
    log_action("email_send", entity="outbox", after={"envoyes": sent, "erreurs": errors}, commit=True)
    if sent == 0 and errors == 0:
        flash("Aucun message en attente.", "success")
    else:
        flash(
            f"Envoi : {sent} envoye(s), {errors} erreur(s).",
            "success" if errors == 0 else "danger",
        )
    if not settings_service.smtp_configured() and errors:
        flash("SMTP non configure : renseignez le serveur dans la configuration ci-dessus.", "warning")
    return redirect(url_for("admin.outbox"))


@admin_bp.route("/emails/<int:message_id>/renvoyer", methods=["POST"])
@login_required
@permission_required(P.SETTINGS_MANAGE)
def outbox_resend(message_id):
    try:
        settings_service.resend(message_id)
    except ValueError as exc:
        flash(str(exc), "danger")
    else:
        flash("Message replace en file d'attente.", "success")
    return redirect(url_for("admin.outbox"))
