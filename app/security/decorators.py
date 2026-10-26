"""Decorateurs de controle d'acces (verifies cote serveur)."""
from functools import wraps

from flask import abort, flash, redirect, request, url_for
from flask_login import current_user, login_required

from app.security.audit import log_action
from app.security.owner import find_admin_by_password, is_owner, require_owner_password


def permission_required(*permissions, mode="all"):
    """Exige une ou plusieurs permissions. journalise le refus en audit."""

    def decorator(func):
        @wraps(func)
        @login_required
        def wrapper(*args, **kwargs):
            if current_user.is_super_admin:
                return func(*args, **kwargs)
            if mode == "all" and hasattr(current_user, "has_all"):
                checker = current_user.has_all
            else:
                checker = getattr(current_user, "has_any", None)
            if checker and checker(*permissions):
                return func(*args, **kwargs)
            log_action(
                "access_denied",
                entity="route",
                reason=f"{request.endpoint} :: permissions={list(permissions)} mode={mode}",
                commit=False,
            )
            from app.extensions import db

            db.session.commit()
            flash("Acces refuse : permissions insuffisantes.", "danger")
            abort(403)

        return wrapper

    return decorator


def owner_only():
    """Exige que l'utilisateur soit proprietaire / super administrateur."""

    def decorator(func):
        @wraps(func)
        @login_required
        def wrapper(*args, **kwargs):
            if not is_owner(current_user):
                flash("Seul le proprietaire peut acceder a cette action.", "danger")
                abort(403)
            return func(*args, **kwargs)

        return wrapper

    return decorator


def admin_password_required():
    """Action destructive : mot de passe d'un administrateur/propriétaire exigé pour TOUT utilisateur,
    administrateur compris. Le champ `owner_password` du formulaire est vérifié côté serveur."""

    def decorator(func):
        @wraps(func)
        @login_required
        def wrapper(*args, **kwargs):
            if request.method != "POST":
                return func(*args, **kwargs)
            from app.extensions import db

            authorizer = find_admin_by_password(request.form.get("owner_password"))
            if authorizer is None:
                log_action(
                    "admin_password_failed",
                    entity="route",
                    reason=f"{request.endpoint} :: mot de passe administrateur invalide",
                    commit=False,
                )
                db.session.commit()
                flash("Suppression refusée : mot de passe administrateur invalide ou absent.", "danger")
                return redirect(request.referrer or url_for("main.dashboard"))
            log_action(
                "admin_password_ok",
                entity="route",
                reason=f"{request.endpoint} :: autorisé par {authorizer.username}",
                commit=False,
            )
            db.session.commit()
            return func(*args, **kwargs)

        return wrapper

    return decorator


def owner_reauth_required():
    """Exige re-authentification par mot de passe du proprietaire (POST)."""

    def decorator(func):
        @wraps(func)
        @login_required
        def wrapper(*args, **kwargs):
            if request.method not in ("POST", "PUT", "PATCH", "DELETE"):
                return func(*args, **kwargs)
            ok, err = require_owner_password()
            if not ok:
                log_action(
                    "owner_reauth_failed",
                    entity="route",
                    reason=f"{request.endpoint} :: {err}",
                    commit=False,
                )
                from app.extensions import db

                db.session.commit()
                flash(err or "Re-authentification proprietaire requise.", "danger")
                ref = request.referrer or url_for("main.dashboard")
                return redirect(ref)
            log_action(
                "owner_reauth_ok",
                entity="route",
                reason=request.endpoint,
                commit=False,
            )
            from app.extensions import db

            db.session.commit()
            return func(*args, **kwargs)

        return wrapper

    return decorator
