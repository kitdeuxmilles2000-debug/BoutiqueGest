"""Authentification : verification des identifiants et ouverture de session."""
from datetime import timedelta

from flask import current_app
from flask_login import current_user

from app.extensions import db
from app.models.base import utcnow
from app.models.user import User, UserSession


def authenticate(username, password):
    """Retourne (user, None) si OK, sinon (None, code_erreur)."""
    user = User.query.filter_by(username=(username or "").strip()).first()
    if user is None:
        return None, "invalid"
    if not user.active:
        return None, "inactive"
    if user.is_locked():
        return None, "locked"

    if not user.check_password(password or ""):
        user.failed_login_count = (user.failed_login_count or 0) + 1
        if user.failed_login_count >= current_app.config.get("LOGIN_MAX_ATTEMPTS", 5):
            user.locked_until = utcnow() + timedelta(
                minutes=current_app.config.get("LOGIN_LOCK_MINUTES", 15)
            )
        db.session.commit()
        return None, "invalid"

    user.failed_login_count = 0
    user.locked_until = None
    user.last_login_at = utcnow()
    db.session.commit()
    return user, None


def open_session(user, device_id=None, ip=None, user_agent=None):
    entry = UserSession(
        user_id=user.id,
        device_id=device_id,
        ip=ip,
        user_agent=(user_agent or "")[:255],
        expires_at=utcnow() + timedelta(hours=current_app.config.get("SESSION_LIFETIME_HOURS", 8)),
    )
    db.session.add(entry)
    db.session.commit()
    return entry


def current_user_has(code):
    return current_user.is_authenticated and current_user.has_permission(code)
