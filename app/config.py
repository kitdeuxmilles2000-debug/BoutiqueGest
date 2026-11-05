"""Configuration de l'application BoutiqueGest."""
import os
from datetime import timedelta

BASE_DIR = os.path.abspath(os.path.dirname(os.path.dirname(__file__)))
INSTANCE_DIR = os.path.join(BASE_DIR, "instance")
DEFAULT_DB_PATH = os.path.join(INSTANCE_DIR, "boutiquegest.db")


def _database_uri():
    database_url = os.environ.get("DATABASE_URL")
    if database_url:
        if database_url.startswith("postgres://"):
            return database_url.replace("postgres://", "postgresql+psycopg2://", 1)
        if database_url.startswith("postgresql://"):
            return database_url.replace("postgresql://", "postgresql+psycopg2://", 1)
        return database_url
    is_render = os.environ.get("RENDER") == "true" or bool(os.environ.get("RENDER_SERVICE_ID"))
    if os.environ.get("FLASK_CONFIG") == "prod" and is_render:
        raise RuntimeError("DATABASE_URL est obligatoire en production; configurez la base Render.")
    return "sqlite:///" + DEFAULT_DB_PATH.replace("\\", "/")


def _int_env(name, default):
    try:
        return int(os.environ.get(name, default))
    except (TypeError, ValueError):
        return default


class Config:
    SECRET_KEY = os.environ.get("SECRET_KEY", "dev-secret-a-changer")

    SQLALCHEMY_DATABASE_URI = _database_uri()
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SQLALCHEMY_ENGINE_OPTIONS = {
        "pool_pre_ping": True,
    }

    # Sessions / securite
    PERMANENT_SESSION_LIFETIME = timedelta(hours=_int_env("SESSION_LIFETIME_HOURS", 8))
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
    SESSION_COOKIE_SECURE = os.environ.get("SESSION_COOKIE_SECURE", "0") == "1"
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
    SYNC_API_TOKEN = os.environ.get("SYNC_API_TOKEN", "")
    CLOUD_READ_ONLY = os.environ.get("CLOUD_READ_ONLY", "0") == "1"

    # Synchronisation des données métier via un fichier privé sur une branche GitHub dédiée.
    GITHUB_SYNC_ENABLED = os.environ.get("GITHUB_SYNC_ENABLED", "0") == "1"
    GITHUB_SYNC_REPOSITORY = os.environ.get("GITHUB_SYNC_REPOSITORY", "")
    GITHUB_SYNC_TOKEN = os.environ.get("GITHUB_SYNC_TOKEN", "")
    GITHUB_SYNC_BRANCH = os.environ.get("GITHUB_SYNC_BRANCH", "boutiquegest-data")
    GITHUB_SYNC_PATH = os.environ.get(
        "GITHUB_SYNC_PATH", "sync/boutiquegest-snapshot.json.gz"
    )
    GITHUB_SYNC_POLL_SECONDS = _int_env("GITHUB_SYNC_POLL_SECONDS", 30)

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
    SQLALCHEMY_ENGINE_OPTIONS = {
        "pool_pre_ping": True,
        "pool_recycle": 3600,
    }
    if Config.SQLALCHEMY_DATABASE_URI.startswith("sqlite:"):
        SQLALCHEMY_ENGINE_OPTIONS["connect_args"] = {
            "timeout": 30,
            "isolation_level": None,  # Autocommit
        }


CONFIG_MAP = {
    "dev": DevConfig,
    "prod": ProdConfig,
    "default": Config,
}
