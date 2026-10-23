"""Configuration de l'application BoutiqueGest."""
import os
from datetime import timedelta

BASE_DIR = os.path.abspath(os.path.dirname(os.path.dirname(__file__)))
INSTANCE_DIR = os.path.join(BASE_DIR, "instance")
DEFAULT_DB_PATH = os.path.join(INSTANCE_DIR, "boutiquegest.db")


def _int_env(name, default):
    try:
        return int(os.environ.get(name, default))
    except (TypeError, ValueError):
        return default


class Config:
    SECRET_KEY = os.environ.get("SECRET_KEY", "dev-secret-a-changer")

    SQLALCHEMY_DATABASE_URI = os.environ.get("DATABASE_URL") or (
        "sqlite:///" + DEFAULT_DB_PATH.replace("\\", "/")
    )
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SQLALCHEMY_ENGINE_OPTIONS = {
        "pool_pre_ping": True,
    }

    # Sessions / securite
    PERMANENT_SESSION_LIFETIME = timedelta(hours=_int_env("SESSION_LIFETIME_HOURS", 8))
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
    SESSION_COOKIE_SECURE = False  # passer a True derriere HTTPS
    WTF_CSRF_ENABLED = True
    WTF_CSRF_TIME_LIMIT = None

    # Authentification
    LOGIN_MAX_ATTEMPTS = _int_env("LOGIN_MAX_ATTEMPTS", 5)
    LOGIN_LOCK_MINUTES = _int_env("LOGIN_LOCK_MINUTES", 15)
    REAUTH_TIMEOUT_SECONDS = _int_env("REAUTH_TIMEOUT_SECONDS", 300)

    # Sauvegardes
    BACKUP_RETENTION = _int_env("BACKUP_RETENTION", 30)
    BACKUP_DIR = os.environ.get("BACKUP_DIR")  # None -> <base>/backups

    # Synchronisation distante (optionnelle ; le local fonctionne sans)
    SYNC_ENABLED = os.environ.get("SYNC_ENABLED", "0") == "1"
    SYNC_REMOTE_URL = os.environ.get("SYNC_REMOTE_URL", "")

    # E-mails (rapport journalier) : optionnel, sinon les messages restent en file
    SMTP_HOST = os.environ.get("SMTP_HOST", "")
    SMTP_PORT = _int_env("SMTP_PORT", 587)
    SMTP_USER = os.environ.get("SMTP_USER", "")
    SMTP_PASSWORD = os.environ.get("SMTP_PASSWORD", "")
    SMTP_SENDER = os.environ.get("SMTP_SENDER", "")
    SMTP_USE_TLS = os.environ.get("SMTP_USE_TLS", "1") == "1"
    REPORT_EMAIL_TO = os.environ.get("REPORT_EMAIL_TO", "")

    # Affichage
    TIMEZONE = os.environ.get("TIMEZONE", "Africa/Kinshasa")
    APP_NAME = "BoutiqueGest"
    APP_VERSION = "0.1.0"


class DevConfig(Config):
    DEBUG = True


class ProdConfig(Config):
    DEBUG = False
    SESSION_COOKIE_SECURE = True


CONFIG_MAP = {
    "dev": DevConfig,
    "prod": ProdConfig,
    "default": Config,
}
