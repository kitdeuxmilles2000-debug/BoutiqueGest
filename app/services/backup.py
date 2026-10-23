"""Sauvegardes locales de la base SQLite.

- Copie par l'API 'backup' de SQLite (coherente meme en mode WAL et sous ecriture).
- Controle d'integrite automatique de chaque sauvegarde.
- Historique de versions + retention configurable.
- L'integrite est verifiee, pas restauree, en production (restauration en test).
"""
import hashlib
import os
import re
import sqlite3
from datetime import datetime

from flask import current_app

from app.config import BASE_DIR
from app.extensions import db
from app.models.base import utcnow

BACKUP_DIR_NAME = "backups"
BACKUP_RE = re.compile(r"^boutiquegest_(\d{8})_(\d{6})\.db$")


def backup_dir():
    configured = current_app.config.get("BACKUP_DIR")
    path = configured or os.path.join(BASE_DIR, BACKUP_DIR_NAME)
    os.makedirs(path, exist_ok=True)
    return path


def _local_db_path():
    uri = current_app.config.get("SQLALCHEMY_DATABASE_URI", "")
    if not uri.startswith("sqlite:"):
        return None
    path = uri.split("sqlite:///", 1)[-1]
    return path or None


def _sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def _integrity_ok(path):
    try:
        con = sqlite3.connect(path)
        try:
            row = con.execute("PRAGMA integrity_check").fetchone()
            return bool(row) and row[0] == "ok"
        finally:
            con.close()
    except sqlite3.Error:
        return False


def create_backup(label="manuel"):
    """Cree une sauvegarde locale et verifie son integrite. Retourne ses metadonnees."""
    src = _local_db_path()
    if not src or not os.path.exists(src):
        raise RuntimeError("La base SQLite locale est introuvable : sauvegarde impossible.")

    now = utcnow()
    filename = f"boutiquegest_{now:%Y%m%d}_{now:%H%M%S}.db"
    dest = os.path.join(backup_dir(), filename)

    # API de sauvegarde SQLite : copie coherente meme si la base est en WAL.
    src_con = sqlite3.connect(src)
    dest_con = sqlite3.connect(dest)
    try:
        with dest_con:
            src_con.backup(dest_con)
    finally:
        src_con.close()
        dest_con.close()

    ok = _integrity_ok(dest)
    return {
        "filename": filename,
        "path": dest,
        "size": os.path.getsize(dest),
        "sha256": _sha256(dest),
        "created_at": now,
        "valid": ok,
        "label": label,
    }


def list_backups():
    """Liste les sauvegardes existantes (plus recente en premier), avec integrite."""
    result = []
    for name in os.listdir(backup_dir()):
        m = BACKUP_RE.match(name)
        if not m:
            continue
        path = os.path.join(backup_dir(), name)
        try:
            created = datetime.strptime(m.group(1) + m.group(2), "%Y%m%d%H%M%S")
        except ValueError:
            created = datetime.fromtimestamp(os.path.getmtime(path))
        result.append({
            "filename": name,
            "path": path,
            "size": os.path.getsize(path),
            "created_at": created,
            "valid": _integrity_ok(path),
        })
    return sorted(result, key=lambda b: b["created_at"], reverse=True)


def purge_old_backups(keep=None):
    """Supprime les sauvegardes au-dela de la retention. Retourne le nombre supprime."""
    if keep is None:
        keep = int(current_app.config.get("BACKUP_RETENTION", 30))
    backups = list_backups()
    removed = 0
    for old in backups[keep:]:
        try:
            os.remove(old["path"])
            removed += 1
        except OSError:
            pass
    return removed


def restore_backup(filename, target_path):
    """Restaure une sauvegarde vers un chemin cible (usage : environnement de test).

    Retourne un rapport d'ouverture (comptage de quelques tables clefs).
    """
    src = os.path.join(backup_dir(), filename)
    if not os.path.exists(src):
        raise FileNotFoundError(f"Sauvegarde introuvable : {filename}")
    if not _integrity_ok(src):
        raise RuntimeError("Sauvegarde corrompue : restauration refusee.")

    os.makedirs(os.path.dirname(os.path.abspath(target_path)), exist_ok=True)
    src_con = sqlite3.connect(src)
    dest_con = sqlite3.connect(target_path)
    try:
        with dest_con:
            src_con.backup(dest_con)
    finally:
        src_con.close()
        dest_con.close()

    rapport = {"fichier": filename, "cible": target_path}
    con = sqlite3.connect(target_path)
    try:
        for table in ("users", "products", "sales", "sales_lines"):
            try:
                rapport[table] = con.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
            except sqlite3.Error:
                rapport[table] = None
    finally:
        con.close()
    return rapport
