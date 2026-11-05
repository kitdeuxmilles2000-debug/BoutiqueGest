"""Helper pour ecrire dans le journal d'audit."""
import json

from flask import has_request_context, request
from flask_login import current_user

from app.extensions import db
from app.models.audit import AuditLog


def _serialize(value):
    if value is None:
        return None
    try:
        return json.dumps(value, ensure_ascii=False, default=str)
    except (TypeError, ValueError):
        return str(value)


def log_action(
    action,
    entity=None,
    entity_uuid=None,
    before=None,
    after=None,
    reason=None,
    approver_id=None,
    user_id=None,
    username=None,
    device_id=None,
    commit=False,
):
    """Ajoute une entree d'audit. Par defaut, ne commit pas (transaction appelante)."""
    ip = None
    if has_request_context():
        ip = request.headers.get("X-Forwarded-For", request.remote_addr)

    if user_id is None and username is None and has_request_context():
        try:
            if current_user.is_authenticated:
                user_id = current_user.id
                username = current_user.username
        except Exception:  # pragma: no cover - contexte de login incomplet
            pass

    entry = AuditLog(
        user_id=user_id,
        username=username,
        action=action,
        entity=entity,
        entity_uuid=entity_uuid,
        ip=ip,
        device_id=device_id,
        value_before=_serialize(before),
        value_after=_serialize(after),
        reason=reason,
        approver_id=approver_id,
    )
    db.session.add(entry)
    if commit:
        db.session.commit()
    return entry
