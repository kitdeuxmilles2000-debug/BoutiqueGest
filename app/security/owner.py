"""Verification du proprietaire pour actions sensibles.

Certaines actions (suppression, restauration, validation d'entrees en attente,
modifications sensibles) exigent une re-authentification du proprietaire.
"""
from flask import request
from flask_login import current_user

from app.security.permissions import P


def is_owner(user):
    if not user or not user.is_authenticated:
        return False
    if getattr(user, "is_super_admin", False):
        return True
    role = getattr(user, "role", None)
    return bool(role and role.name == "proprietaire")


def is_admin_like(user):
    if not user or not user.is_authenticated:
        return False
    if getattr(user, "is_super_admin", False):
        return True
    role = getattr(user, "role", None)
    if not role:
        return False
    return role.name in ("proprietaire", "administrateur")


def is_strict_admin_like(user):
    if not user or not user.is_authenticated:
        return False
    if getattr(user, "is_super_admin", False):
        return True
    role = getattr(user, "role", None)
    if not role:
        return False
    return role.name in ("proprietaire", "administrateur")


def find_admin_by_password(pwd):
    """Retourne l'administrateur (super admin, propriétaire ou administrateur actif) dont c'est le mot de passe."""
    pwd = (pwd or "").strip()
    if not pwd:
        return None
    from app.models.user import User

    admin_user = User.query.filter(
        User.active.is_(True),
        (User.role.has(is_super_admin=True))
        | (User.role.has(name="proprietaire"))
        | (User.role.has(name="administrateur")),
    ).all()
    for au in admin_user:
        if au.check_password(pwd):
            return au
    return None


def check_admin_password(pwd):
    """Vrai si `pwd` correspond au mot de passe d'un super admin, propriétaire ou administrateur."""
    return find_admin_by_password(pwd) is not None


def require_owner_password():
    """Vérifie le mot de passe propriétaire/administrateur selon la règle:
    - super_admin/propriétaire/administrateur : pas de demande de mot de passe
    - autres utilisateurs (vendeur, etc.) : doit fournir 'owner_password' (mot de passe d'un administrateur/propriétaire)
    """
    if is_admin_like(current_user):
        return True, None
    pwd = (request.form.get("owner_password") or "").strip()
    if not pwd:
        return False, "Mot de passe administrateur/propriétaire requis pour cette action."
    if check_admin_password(pwd):
        return True, None
    return False, "Mot de passe administrateur/propriétaire invalide."
