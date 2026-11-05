"""Authentification : connexion, deconnexion, mot de passe, reauthentification."""
from flask import Blueprint, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required, login_user, logout_user

from app.extensions import db
from app.security import session as sess
from app.security.audit import log_action
from app.services import auth as auth_service
from app.services import notifications as notifications_service

auth_bp = Blueprint("auth", __name__)

ERROR_MESSAGES = {
    "invalid": "Identifiants incorrects.",
    "inactive": "Ce compte est desactive.",
    "locked": "Compte temporairement verrouille. Reessayez plus tard.",
}


@auth_bp.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for("main.dashboard"))

    if request.method == "POST":
        username = request.form.get("username", "")
        password = request.form.get("password", "")
        user, error = auth_service.authenticate(username, password)
        if user is not None:
            login_user(user, remember=False)
            sess.clear_reauth()
            auth_service.open_session(
                user,
                ip=request.remote_addr,
                user_agent=request.headers.get("User-Agent"),
            )
            log_action(
                "login",
                entity="user",
                entity_uuid=user.uuid,
                user_id=user.id,
                username=user.username,
                commit=True,
            )
            if user.must_change_password:
                flash("Veuillez changer votre mot de passe par defaut.", "warning")
                return redirect(url_for("auth.change_password"))
            return redirect(url_for("main.dashboard"))

        log_action(
            "login_failed",
            entity="user",
            username=username,
            reason=error,
            commit=True,
        )
        flash(ERROR_MESSAGES.get(error, "Echec de connexion."), "danger")

    return render_template("auth/login.html")


@auth_bp.route("/logout", methods=["POST"])
@login_required
def logout():
    log_action("logout", entity="user", entity_uuid=current_user.uuid, commit=True)
    logout_user()
    sess.clear_reauth()
    flash("Vous avez ete deconnecte.", "success")
    return redirect(url_for("auth.login"))


@auth_bp.route("/change-password", methods=["GET", "POST"])
@login_required
def change_password():
    if request.method == "POST":
        current = request.form.get("current_password", "")
        new = request.form.get("new_password", "")
        confirm = request.form.get("confirm_password", "")

        if not current_user.check_password(current):
            flash("Mot de passe actuel incorrect.", "danger")
        elif len(new) < 8:
            flash("Le nouveau mot de passe doit contenir au moins 8 caracteres.", "danger")
        elif new != confirm:
            flash("Les deux mots de passe ne correspondent pas.", "danger")
        else:
            current_user.set_password(new)
            current_user.must_change_password = False
            db.session.commit()
            log_action(
                "password_change",
                entity="user",
                entity_uuid=current_user.uuid,
                commit=True,
            )
            flash("Mot de passe modifie avec succes.", "success")
            notifications_service.notify_password_changed(current_user)
            return redirect(url_for("main.dashboard"))

    return render_template("auth/change_password.html")


@auth_bp.route("/reauth", methods=["POST"])
@login_required
def reauth():
    password = request.form.get("password", "")
    if current_user.check_password(password):
        sess.mark_reauth()
        log_action("reauth", entity="user", entity_uuid=current_user.uuid, commit=True)
        flash("Reauthentification reussie.", "success")
    else:
        log_action(
            "reauth_failed",
            entity="user",
            entity_uuid=current_user.uuid,
            reason="Mot de passe incorrect",
            commit=True,
        )
        flash("Mot de passe incorrect.", "danger")
    return redirect(request.referrer or url_for("main.dashboard"))
