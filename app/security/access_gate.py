"""Contrôle d'accès renforcé: sections réservées aux vendeurs + déverrouillage admin.

Les utilisateurs au rôle « vendeur » (profil limité) n'accèdent directement qu'aux
modules autorisés (POS, Produits consultation, Caisse, Dépenses, Rapports).
Les autres sections et l'export de rapports peuvent être déverrouillés
temporairement en saisissant le mot de passe d'un administrateur/propriétaire.
"""
from __future__ import annotations

import time
from functools import wraps

from flask import flash, redirect, request, session, url_for
from flask_login import current_user

from app.security.owner import is_admin_like

UNLOCK_SESSION_KEY = "admin_access_unlocked_at"
UNLOCK_TTL_SECONDS = 30 * 60  # 30 minutes

# Endpoints toujours autorisés (même pour vendeur restreint, hors déverrouillage)
ALLOWED_ENDPOINT_PREFIXES = (
    "auth.",
    "static",
    "notifications.",
    "pos.",
    "cash.",
    "expenses.",
)
ALLOWED_ENDPOINTS = {
    "main.dashboard",
    "main.index",
    "products.index",
    "products.detail",
    "reports.index",
    "admin.access_unlock",  # page de déverrouillage
    "admin.access_lock",
}


def is_restricted_vendor(user=None) -> bool:
    user = user or current_user
    if not user or not getattr(user, "is_authenticated", False):
        return False
    if is_admin_like(user):
        return False
    role = getattr(user, "role", None)
    return bool(role and role.name == "vendeur")


def is_access_unlocked() -> bool:
    ts = session.get(UNLOCK_SESSION_KEY)
    if not ts:
        return False
    try:
        return (time.time() - float(ts)) <= UNLOCK_TTL_SECONDS
    except (TypeError, ValueError):
        return False


def set_access_unlocked():
    session[UNLOCK_SESSION_KEY] = time.time()


def clear_access_unlocked():
    session.pop(UNLOCK_SESSION_KEY, None)


def endpoint_allowed_for_vendor(endpoint: str | None) -> bool:
    if not endpoint:
        return True
    if endpoint in ALLOWED_ENDPOINTS:
        return True
    return any(endpoint.startswith(p) for p in ALLOWED_ENDPOINT_PREFIXES)


def require_unlock_redirect(next_url=None):
    target = next_url or request.full_path or request.path
    if target and target.endswith("?"):
        target = target[:-1]
    return redirect(url_for("admin.access_unlock", next=target))


def vendor_gate_check():
    """À utiliser en before_request: redirige les vendeurs non déverrouillés."""
    if not is_restricted_vendor():
        return None
    if is_access_unlocked():
        return None
    endpoint = request.endpoint
    if endpoint_allowed_for_vendor(endpoint):
        return None
    # POST sur sections restreintes: exiger aussi le déverrouillage
    flash("Accès protégé : saisissez le mot de passe administrateur pour continuer.", "warning")
    return require_unlock_redirect()


def reports_export_gate():
    """Garde spécifique export rapports pour vendeurs restreints."""
    if not is_restricted_vendor():
        return None
    if is_access_unlocked():
        return None
    flash("L'export des rapports nécessite le mot de passe administrateur.", "warning")
    return require_unlock_redirect()
