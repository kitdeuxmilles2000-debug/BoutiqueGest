"""Historique des points de restauration SQLite horodatés."""
import os
import re
import sqlite3
from datetime import datetime

from flask import current_app

from app.extensions import db
from app.models.base import utcnow

SNAPSHOT_RE = re.compile(r"^boutiquegest_\d{4}-\d{2}-\d{2}_\d{2}-\d{2}-\d{2}(?:_[A-Za-z0-9_-]+)?\.db$")


def history_dir():
    d = current_app.config.get("HISTORY_DIR")
    if not d:
        d = os.path.join(current_app.root_path, "..", "history")
    d = os.path.abspath(d)
    os.makedirs(d, exist_ok=True)
    return d


def db_path():
    uri = current_app.config.get("SQLALCHEMY_DATABASE_URI", "")
    if not uri.startswith("sqlite:"):
        raise RuntimeError("Les points de restauration sont disponibles uniquement pour SQLite.")
    path = uri.split("sqlite:///", 1)[-1]
    if not path or path == ":memory:":
        raise RuntimeError("Le chemin de la base SQLite est introuvable.")
    return os.path.abspath(path)


def _integrity_ok(path):
    try:
        connection = sqlite3.connect(path)
        try:
            row = connection.execute("PRAGMA integrity_check").fetchone()
            return bool(row) and row[0] == "ok"
        finally:
            connection.close()
    except sqlite3.Error:
        return False


def create_snapshot(label="auto"):
    src = db_path()
    if not os.path.exists(src):
        raise RuntimeError("Base de données introuvable.")
    stamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    name = f"boutiquegest_{stamp}.db"
    if label and label != "auto":
        safe = "".join(c for c in label if c.isalnum() or c in ("-", "_"))[:30]
        if safe:
            name = f"boutiquegest_{stamp}_{safe}.db"
    dst = os.path.join(history_dir(), name)
    src_connection = sqlite3.connect(src)
    dst_connection = sqlite3.connect(dst)
    try:
        with dst_connection:
            src_connection.backup(dst_connection)
    finally:
        src_connection.close()
        dst_connection.close()
    if not _integrity_ok(dst):
        os.remove(dst)
        raise RuntimeError("Le point de restauration a échoué au contrôle d'intégrité.")
    return {"filename": name, "path": dst, "size": os.path.getsize(dst), "created_at": utcnow()}


def list_snapshots():
    d = history_dir()
    items = []
    for name in os.listdir(d):
        if name.endswith(".db") and not name.endswith(".sha256"):
            p = os.path.join(d, name)
            try:
                items.append({
                    "filename": name,
                    "path": p,
                    "size": os.path.getsize(p),
                    "mtime": datetime.fromtimestamp(os.path.getmtime(p)),
                })
            except OSError:
                continue
    items.sort(key=lambda x: x["mtime"], reverse=True)
    return items


def restore_snapshot(filename, reason=""):
    """Restaure depuis history/ vers la base active. Appeler APRÈS vérification propriétaire."""
    if not SNAPSHOT_RE.fullmatch(filename):
        raise ValueError("Nom de fichier invalide.")
    src = os.path.join(history_dir(), filename)
    if not os.path.exists(src):
        raise ValueError("Snapshot introuvable.")
    if not _integrity_ok(src):
        raise RuntimeError("Point de restauration corrompu : restauration refusée.")
    dst = db_path()
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    pre = create_snapshot(label="pre-restore")
    db.session.remove()
    db.engine.dispose()
    src_connection = sqlite3.connect(src)
    dst_connection = sqlite3.connect(dst)
    try:
        with dst_connection:
            src_connection.backup(dst_connection)
    finally:
        src_connection.close()
        dst_connection.close()
    return {"restored_from": filename, "pre_restore": pre["filename"], "reason": reason}
