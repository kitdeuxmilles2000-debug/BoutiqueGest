from flask import Blueprint, jsonify, redirect, render_template, request, url_for
from flask_login import current_user, login_required

from app.extensions import db
from app.models.notifications import Notification, NOTIFICATION_TYPE_LABELS
from app.services import notifications as notif_service
from app.services.pagination import paginate

notifications_bp = Blueprint("notifications", __name__, url_prefix="/notifications")


@notifications_bp.route("/")
@login_required
def index():
    notif_service.sync_alerts()
    pager = paginate(
        Notification.query.filter_by(dismissed=False).order_by(Notification.created_at.desc())
    )
    unread = Notification.query.filter_by(dismissed=False, read=False).count()
    return render_template("notifications/index.html", notes=pager.items, pager=pager, unread=unread)


@notifications_bp.route("/api/list")
@login_required
def api_list():
    notif_service.sync_alerts()
    unread_count = Notification.query.filter_by(dismissed=False, read=False).count()
    notes = (
        Notification.query.filter_by(dismissed=False)
        .order_by(Notification.created_at.desc())
        .limit(20)
        .all()
    )
    return jsonify(
        {
            "count": unread_count,
            "items": [
                {
                    "id": n.id,
                    "type": n.type,
                    "label": NOTIFICATION_TYPE_LABELS.get(n.type, n.type),
                    "title": n.title,
                    "message": n.message,
                    "link": n.link,
                    "read": n.read,
                    "priority": n.priority,
                    "created_at": n.created_at.isoformat() if n.created_at else None,
                }
                for n in notes
            ],
        }
    )


@notifications_bp.route("/<int:nid>/lire", methods=["POST"])
@login_required
def mark_read(nid):
    n = db.session.get(Notification, nid)
    if n:
        n.read = True
        db.session.commit()
    if request.is_json:
        return jsonify({"ok": True})
    return redirect(request.referrer or url_for("notifications.index"))


@notifications_bp.route("/lire-tout", methods=["POST"])
@login_required
def mark_all_read():
    Notification.query.filter_by(dismissed=False, read=False).update({"read": True})
    db.session.commit()
    if request.is_json:
        return jsonify({"ok": True})
    return redirect(request.referrer or url_for("notifications.index"))


@notifications_bp.route("/<int:nid>/ignorer", methods=["POST"])
@login_required
def dismiss(nid):
    n = db.session.get(Notification, nid)
    if n:
        n.dismissed = True
        n.read = True
        db.session.commit()
    if request.is_json:
        return jsonify({"ok": True})
    return redirect(request.referrer or url_for("notifications.index"))
