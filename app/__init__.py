"""Application factory de BoutiqueGest."""
import os

from flask import Flask, render_template

from app.config import CONFIG_MAP
from app.extensions import csrf, db, login_manager, migrate

__version__ = "0.1.0"


def create_app(config_name=None):
    config_name = config_name or os.environ.get("FLASK_CONFIG", "dev")
    config_class = CONFIG_MAP.get(config_name, CONFIG_MAP["default"])

    app = Flask(__name__, instance_relative_config=True)
    app.config.from_object(config_class)
    os.makedirs(app.instance_path, exist_ok=True)

    _register_extensions(app)
    _register_blueprints(app)
    _register_context(app)
    _register_errors(app)

    from app.cli import register_cli

    register_cli(app)

    return app


def _register_extensions(app):
    db.init_app(app)
    migrate.init_app(app, db)
    csrf.init_app(app)
    login_manager.init_app(app)

    from app.models.user import User

    @login_manager.user_loader
    def load_user(user_id):
        try:
            return db.session.get(User, int(user_id))
        except (TypeError, ValueError):
            return None


def _register_blueprints(app):
    from app.routes.admin import admin_bp
    from app.routes.auth import auth_bp
    from app.routes.cash import cash_bp
    from app.routes.credits import credits_bp
    from app.routes.expenses import expenses_bp
    from app.routes.main import main_bp
    from app.routes.partners import partners_bp
    from app.routes.pos import pos_bp
    from app.routes.products import products_bp
    from app.routes.purchases import purchases_bp
    from app.routes.reports import reports_bp
    from app.routes.sales import sales_bp
    from app.routes.stock import stock_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(main_bp)
    app.register_blueprint(products_bp)
    app.register_blueprint(purchases_bp)
    app.register_blueprint(stock_bp)
    app.register_blueprint(cash_bp)
    app.register_blueprint(sales_bp)
    app.register_blueprint(pos_bp)
    app.register_blueprint(partners_bp)
    app.register_blueprint(expenses_bp)
    app.register_blueprint(credits_bp)
    app.register_blueprint(reports_bp)
    app.register_blueprint(admin_bp)


def _register_context(app):
    from decimal import Decimal

    from app.models.settings import OUTBOX_STATUS_BADGES
    from app.models.sync import SYNC_STATUS_BADGES
    from app.security.permissions import P, PERMISSION_LABELS

    @app.template_filter("num")
    def fmt_num(value, decimals=2):
        try:
            return f"{float(value or 0):,.{decimals}f}".replace(",", " ")
        except (TypeError, ValueError):
            return value

    @app.template_filter("qty")
    def fmt_qty(value):
        try:
            normalized = Decimal(str(value if value is not None else 0)).normalize()
            if normalized == normalized.to_integral():
                return str(normalized.quantize(Decimal(1)))
            return format(normalized, "f")
        except Exception:
            return value

    @app.context_processor
    def inject_globals():
        from datetime import date

        from flask_login import current_user

        from app.security.owner import is_owner

        return {
            "P": P,
            "PERMISSION_LABELS": PERMISSION_LABELS,
            "app_name": app.config.get("APP_NAME", "BoutiqueGest"),
            "app_version": app.config.get("APP_VERSION", __version__),
            "SYNC_STATUS_BADGES": SYNC_STATUS_BADGES,
            "OUTBOX_STATUS_BADGES": OUTBOX_STATUS_BADGES,
            "is_owner": lambda: is_owner(current_user),
            "now_date": date.today(),
        }


def _register_errors(app):
    @app.errorhandler(401)
    def unauthorized(error):  # noqa: ARG001
        return render_template("errors/401.html"), 401

    @app.errorhandler(403)
    def forbidden(error):  # noqa: ARG001
        return render_template("errors/403.html"), 403

    @app.errorhandler(404)
    def not_found(error):  # noqa: ARG001
        return render_template("errors/404.html"), 404

    @app.errorhandler(500)
    def server_error(error):  # noqa: ARG001
        db.session.rollback()
        return render_template("errors/500.html"), 500
