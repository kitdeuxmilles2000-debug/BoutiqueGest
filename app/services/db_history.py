"""Historique de la base de données (snapshots horodatés).

Copie automatique de instance/boutiquegest.db vers history/ avec
boutiquegest_YYYY-MM-DD_HH-MM-SS.db.
Restauration protégée par mot de passe propriétaire + audit.
"""
import os
import shutil
from datetime import datetime

from flask import current_app

from app.config import DEFAULT_DB_PATH, INSTANCE_DIR
from app.models.base import utcnow


def history_dir():
    base = os.path.abspath(os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__)))))
    d = os.path.join(base, "history")
    os.makedirs(d, exist_ok=True)
    return d


def db_path():
    return DEFAULT_DB_PATH


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
    shutil.copy2(src, dst)
    # aussi créer un .sha256
    try:
        import hashlib
        h = hashlib.sha256(open(dst, "rb").read()).hexdigest()
        with open(dst + ".sha256", "w", encoding="utf-8") as f:
            f.write(h)
    except Exception:
        pass
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
    if "/" in filename or "\\" in filename or ".." in filename:
        raise ValueError("Nom de fichier invalide.")
    src = os.path.join(history_dir(), filename)
    if not os.path.exists(src):
        raise ValueError("Snapshot introuvable.")
    dst = db_path()
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    # Sauvegarde de sécurité avant restauration
    pre = create_snapshot(label="pre-restore")
    shutil.copy2(src, dst)
    return {"restored_from": filename, "pre_restore": pre["filename"], "reason": reason}
