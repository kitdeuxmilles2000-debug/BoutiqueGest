"""Gestion de la reauthentification pour les actions sensibles."""
from datetime import datetime

from flask import current_app, session

from app.models.base import utcnow

REAUTH_KEY = "reauth_at"


def mark_reauth():
    session[REAUTH_KEY] = utcnow().isoformat()


def clear_reauth():
    session.pop(REAUTH_KEY, None)


def is_reauth_valid(max_seconds=None):
    raw = session.get(REAUTH_KEY)
    if not raw:
        return False
    try:
        moment = datetime.fromisoformat(raw)
    except (TypeError, ValueError):
        return False
    if max_seconds is None:
        max_seconds = current_app.config.get("REAUTH_TIMEOUT_SECONDS", 300)
    return (utcnow() - moment).total_seconds() <= max_seconds
