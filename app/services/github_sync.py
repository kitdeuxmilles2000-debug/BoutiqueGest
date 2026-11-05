"""Synchronisation automatique des instantanés métier via l'API GitHub."""
import base64
import gzip
import io
import json
import os
import shutil
import subprocess
import tempfile
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone

from flask import current_app, request
from sqlalchemy.exc import SQLAlchemyError

from app.extensions import db
from app.models.base import utcnow
from app.models.user import get_setting, set_setting
from app.services import sync as snapshot_sync

MAX_SNAPSHOT_BYTES = 900_000
API_ROOT = "https://api.github.com"


class GitHubConflictError(RuntimeError):
    """Le fichier distant a changé pendant la publication."""


def _parse_datetime(value):
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is not None:
        parsed = parsed.astimezone(timezone.utc).replace(tzinfo=None)
    return parsed


def _git_repo_url(repo):
    return f"https://github.com/{repo}.git"


def _git_fallback_available():
    try:
        result = subprocess.run(["git", "--version"], capture_output=True, timeout=5)
        return result.returncode == 0
    except Exception:
        return False


def _settings():
    repo = current_app.config.get("GITHUB_SYNC_REPOSITORY", "").strip()
    token = current_app.config.get("GITHUB_SYNC_TOKEN", "").strip()
    branch = current_app.config.get("GITHUB_SYNC_BRANCH", "boutiquegest-data").strip()
    path = current_app.config.get(
        "GITHUB_SYNC_PATH", "sync/boutiquegest-snapshot.json.gz"
    ).strip()
    enabled = current_app.config.get("GITHUB_SYNC_ENABLED")
    if enabled is None:
        # Auto-enable if repo detected
        enabled = bool(repo)
    if not enabled or not repo:
        return None
    if len(repo.split("/")) != 2 or not all(repo.split("/")):
        raise ValueError("GITHUB_SYNC_REPOSITORY doit être au format propriétaire/dépôt.")
    if not branch or not path:
        raise ValueError("La branche et le chemin du fichier GitHub sont obligatoires.")
    mode = "api" if token else ("git" if _git_fallback_available() else None)
    if mode is None:
        return None
    return repo, token, branch, path, mode


def _api_request(method, endpoint, token, payload=None):
    body = None
    if payload is not None:
        body = json.dumps(payload, separators=(",", ":")).encode("utf-8")
    request = urllib.request.Request(
        f"{API_ROOT}{endpoint}",
        data=body,
        headers={
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {token}",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "BoutiqueGest",
            "Content-Type": "application/json",
        },
        method=method,
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            content = response.read(2_000_001)
            if len(content) > 2_000_000:
                raise RuntimeError("Réponse GitHub trop volumineuse.")
            if not content:
                return {}
            return json.loads(content.decode("utf-8"))
    except urllib.error.HTTPError as exc:
        if exc.code in {409, 422}:
            raise GitHubConflictError(f"Conflit de version GitHub ({exc.code}).") from exc
        if exc.code == 404:
            return None
        details = exc.read(2048).decode("utf-8", errors="replace")
        try:
            details = json.loads(details).get("message", details)
        except json.JSONDecodeError:
            pass
        raise RuntimeError(f"GitHub a répondu {exc.code} : {details}") from exc


def _contents_endpoint(repo, path, branch):
    encoded_path = urllib.parse.quote(path, safe="/")
    encoded_branch = urllib.parse.quote(branch, safe="")
    return f"/repos/{repo}/contents/{encoded_path}?ref={encoded_branch}"


def _assert_private_repository(repo, token):
    repository = _api_request("GET", f"/repos/{repo}", token)
    if not isinstance(repository, dict):
        raise RuntimeError("Dépôt GitHub introuvable ou inaccessible.")
    if repository.get("private") is not True:
        raise RuntimeError(
            "La synchronisation des données métier est bloquée : le dépôt GitHub doit être privé."
        )
    return repository


def _git_env():
    env = os.environ.copy()
    env["GIT_TERMINAL_PROMPT"] = "0"
    return env


def _git_run(args, cwd, check=True):
    result = subprocess.run(
        ["git"] + args,
        cwd=cwd,
        capture_output=True,
        text=True,
        timeout=120,
        env=_git_env(),
    )
    if check and result.returncode != 0:
        msg = (result.stderr or result.stdout or "").strip()[:500]
        raise RuntimeError(f"Git: {msg}")
    return result


def _git_read_snapshot(settings):
    repo, token, branch, path, mode = settings
    tmp = tempfile.mkdtemp(prefix="bg_sync_")
    try:
        repo_url = _git_repo_url(repo)
        # Try clone branch; if it doesn't exist, return None
        clone = _git_run(["clone", "--depth", "1", "--branch", branch, repo_url, tmp], cwd=tempfile.gettempdir(), check=False)
        if clone.returncode != 0:
            # Branch might not exist yet
            return None, [], None
        file_path = os.path.join(tmp, *path.split("/"))
        if not os.path.exists(file_path):
            return None, [], None
        with open(file_path, "rb") as f:
            compressed = f.read()
        with gzip.GzipFile(fileobj=io.BytesIO(compressed)) as stream:
            content = stream.read(100 * 1024 * 1024 + 1)
        if len(content) > 100 * 1024 * 1024:
            raise ValueError("Instantané GitHub décompressé trop volumineux.")
        document = json.loads(content.decode("utf-8"))
        if (
            not isinstance(document, dict)
            or document.get("format") != "boutiquegest-snapshot-v1"
            or not isinstance(document.get("snapshot"), dict)
            or not isinstance(document.get("tombstones", []), list)
        ):
            raise ValueError("Format d'instantané GitHub invalide.")
        snapshot_sync._validate_snapshot(
            document["snapshot"], snapshot_sync._models_by_table()
        )
        tombstones = _validate_tombstones(document.get("tombstones", []))
        # Get HEAD sha as reference
        sha_res = _git_run(["rev-parse", "HEAD"], cwd=tmp)
        sha = sha_res.stdout.strip()
        return document["snapshot"], tombstones, sha
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def _git_write_snapshot(settings, snapshot, tombstones, sha):
    repo, token, branch, path, mode = settings
    document = {
        "format": "boutiquegest-snapshot-v1",
        "updated_at": utcnow().isoformat(),
        "snapshot": snapshot,
        "tombstones": tombstones,
    }
    content = gzip.compress(
        json.dumps(document, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    )
    if len(content) > MAX_SNAPSHOT_BYTES:
        raise RuntimeError(
            "L'instantané compressé dépasse la limite de 900 Ko de synchronisation GitHub."
        )
    tmp = tempfile.mkdtemp(prefix="bg_sync_")
    try:
        repo_url = _git_repo_url(repo)
        # Try to clone branch; if not exists, create it
        clone = _git_run(["clone", "--depth", "1", "--branch", branch, repo_url, tmp], cwd=tempfile.gettempdir(), check=False)
        if clone.returncode != 0:
            # Clone default and create branch
            _git_run(["clone", "--depth", "1", repo_url, tmp], cwd=tempfile.gettempdir())
            # Try to create orphan branch
            _git_run(["checkout", "--orphan", branch], cwd=tmp, check=False)
            _git_run(["rm", "-rf", "."], cwd=tmp, check=False)
        else:
            _git_run(["checkout", branch], cwd=tmp, check=False)
        file_path = os.path.join(tmp, *path.split("/"))
        os.makedirs(os.path.dirname(file_path), exist_ok=True)
        with open(file_path, "wb") as f:
            f.write(content)
        _git_run(["add", path], cwd=tmp)
        # Check if there are changes
        status = _git_run(["status", "--porcelain"], cwd=tmp)
        if not status.stdout.strip():
            return {"commit": {"sha": sha or "no-change"}, "skipped": True}
        _git_run(["-c", "user.name=BoutiqueGest", "-c", "user.email=sync@local", "commit", "-m", "Synchronisation automatique des données BoutiqueGest"], cwd=tmp)
        push = _git_run(["push", "origin", branch], cwd=tmp, check=False)
        if push.returncode != 0:
            # Try to pull and retry (simple conflict handling)
            _git_run(["pull", "--rebase", "origin", branch], cwd=tmp, check=False)
            push2 = _git_run(["push", "origin", branch], cwd=tmp, check=False)
            if push2.returncode != 0:
                raise RuntimeError(f"Git push échoué: {(push2.stderr or push2.stdout)[:300]}")
        sha_res = _git_run(["rev-parse", "HEAD"], cwd=tmp)
        return {"commit": {"sha": sha_res.stdout.strip()}}
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def _read_snapshot(settings):
    repo, token, branch, path, mode = settings
    if mode == "git":
        return _git_read_snapshot(settings)
    _assert_private_repository(repo, token)
    response = _api_request(
        "GET", _contents_endpoint(repo, path, branch), token
    )
    if response is None:
        return None, [], None
    try:
        if not isinstance(response, dict) or not response.get("sha"):
            raise ValueError("Métadonnées du fichier GitHub absentes.")
        encoded = response.get("content", "").replace("\n", "")
        compressed = base64.b64decode(encoded, validate=True)
        with gzip.GzipFile(fileobj=io.BytesIO(compressed)) as stream:
            content = stream.read(100 * 1024 * 1024 + 1)
        if len(content) > 100 * 1024 * 1024:
            raise ValueError("Instantané GitHub décompressé trop volumineux.")
        document = json.loads(content.decode("utf-8"))
        if (
            not isinstance(document, dict)
            or document.get("format") != "boutiquegest-snapshot-v1"
            or not isinstance(document.get("snapshot"), dict)
            or not isinstance(document.get("tombstones", []), list)
        ):
            raise ValueError("Format d'instantané GitHub invalide.")
        snapshot_sync._validate_snapshot(
            document["snapshot"], snapshot_sync._models_by_table()
        )
        tombstones = _validate_tombstones(document.get("tombstones", []))
        return document["snapshot"], tombstones, response["sha"]
    except (ValueError, OSError, EOFError, json.JSONDecodeError, TypeError, AttributeError) as exc:
        raise RuntimeError(f"Instantané GitHub illisible : {exc}") from exc


def _ensure_branch(repo, token, branch):
    repository = _assert_private_repository(repo, token)
    encoded_branch = urllib.parse.quote(branch, safe="")
    ref_endpoint = f"/repos/{repo}/git/ref/heads/{encoded_branch}"
    if _api_request("GET", ref_endpoint, token) is not None:
        return

    if not isinstance(repository, dict) or not repository.get("default_branch"):
        raise RuntimeError("Impossible de trouver la branche principale GitHub.")
    base_branch = urllib.parse.quote(repository["default_branch"], safe="")
    base_ref = _api_request(
        "GET", f"/repos/{repo}/git/ref/heads/{base_branch}", token
    )
    if not isinstance(base_ref, dict) or not base_ref.get("object", {}).get("sha"):
        raise RuntimeError("Impossible de lire la branche source du dépôt GitHub.")
    created = _api_request(
        "POST",
        f"/repos/{repo}/git/refs",
        token,
        {"ref": f"refs/heads/{branch}", "sha": base_ref["object"]["sha"]},
    )
    if created is None:
        raise RuntimeError(f"Impossible de créer la branche GitHub {branch}.")


def _write_snapshot(settings, snapshot, tombstones, sha):
    repo, token, branch, path, mode = settings
    if mode == "git":
        return _git_write_snapshot(settings, snapshot, tombstones, sha)
    document = {
        "format": "boutiquegest-snapshot-v1",
        "updated_at": utcnow().isoformat(),
        "snapshot": snapshot,
        "tombstones": tombstones,
    }
    content = gzip.compress(
        json.dumps(document, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    )
    if len(content) > MAX_SNAPSHOT_BYTES:
        raise RuntimeError(
            "L'instantané compressé dépasse la limite de 900 Ko de synchronisation GitHub."
        )

    _ensure_branch(repo, token, branch)
    payload = {
        "message": "Synchronisation automatique des données BoutiqueGest",
        "content": base64.b64encode(content).decode("ascii"),
        "branch": branch,
    }
    if sha:
        payload["sha"] = sha
    encoded_path = urllib.parse.quote(path, safe="/")
    endpoint = f"/repos/{repo}/contents/{encoded_path}"
    return _api_request("PUT", endpoint, token, payload)


def _snapshots_equal(left, right):
    models = snapshot_sync._models_by_table()

    def normalized(snapshot):
        user_uuids = {row["id"]: row["uuid"] for row in snapshot["users"]}
        result = {
            "users": sorted(
                (row["uuid"], row["full_name"]) for row in snapshot["users"]
            )
        }
        for table_name, model in models.items():
            rows = []
            for row in snapshot["tables"][table_name]:
                values = {}
                for column in model.__table__.columns:
                    name = column.name
                    if name == "id":
                        continue
                    value = row[name]
                    if column.foreign_keys and value is not None:
                        target = next(iter(column.foreign_keys)).column.table.name
                        if target == "users":
                            value = user_uuids.get(value)
                        elif target in snapshot["tables"]:
                            value = {
                                item["id"]: item["uuid"]
                                for item in snapshot["tables"][target]
                            }.get(value)
                    values[name] = value
                rows.append(values)
            result[table_name] = sorted(
                rows, key=lambda value: value["uuid"]
            )
        return result

    return normalized(left) == normalized(right)


def _validate_tombstones(tombstones):
    seen = set()
    validated = []
    for tombstone in tombstones:
        if (
            not isinstance(tombstone, dict)
            or set(tombstone) != {"table", "uuid", "deleted_at"}
            or tombstone["table"] not in snapshot_sync.SNAPSHOT_TABLES
            or not isinstance(tombstone["uuid"], str)
            or not isinstance(tombstone["deleted_at"], str)
        ):
            raise ValueError("Marqueur de suppression GitHub invalide.")
        _parse_datetime(tombstone["deleted_at"])
        key = (tombstone["table"], tombstone["uuid"])
        if key in seen:
            raise ValueError("Marqueur de suppression GitHub en double.")
        seen.add(key)
        validated.append(tombstone)
    return validated


def _merge_tombstones(*groups):
    latest = {}
    for tombstone in (item for group in groups for item in (group or [])):
        key = (tombstone["table"], tombstone["uuid"])
        current = latest.get(key)
        if current is None or _parse_datetime(tombstone["deleted_at"]) > _parse_datetime(
            current["deleted_at"]
        ):
            latest[key] = tombstone
    return sorted(latest.values(), key=lambda item: (item["table"], item["uuid"]))


def _stored_tombstones():
    raw = get_setting("sync.github_tombstones", "[]")
    try:
        tombstones = json.loads(raw)
    except (TypeError, json.JSONDecodeError) as exc:
        raise RuntimeError("Les marqueurs locaux de suppression sont invalides.") from exc
    if not isinstance(tombstones, list):
        raise RuntimeError("Les marqueurs locaux de suppression sont invalides.")
    return _validate_tombstones(tombstones)


def _find_local_deletions(remote_snapshot):
    last_sync = get_setting("sync.github_last_sync_at")
    if not last_sync:
        return []
    try:
        last_sync_at = _parse_datetime(last_sync)
    except ValueError as exc:
        raise RuntimeError("La date de dernière synchronisation GitHub est invalide.") from exc

    local_snapshot = snapshot_sync.build_snapshot()
    local_uuids = {
        table: {row["uuid"] for row in rows}
        for table, rows in local_snapshot["tables"].items()
    }
    detected = []
    for table, rows in remote_snapshot["tables"].items():
        for row in rows:
            if row["uuid"] in local_uuids[table]:
                continue
            created_at = _parse_datetime(row["created_at"])
            updated_at = _parse_datetime(row["updated_at"])
            if created_at <= last_sync_at and updated_at <= last_sync_at:
                detected.append(
                    {
                        "table": table,
                        "uuid": row["uuid"],
                        "deleted_at": last_sync_at.isoformat(),
                    }
                )
    return detected


def _apply_tombstones(tombstones):
    if not tombstones:
        return
    models = snapshot_sync._models_by_table()
    by_table = {}
    for tombstone in tombstones:
        by_table.setdefault(tombstone["table"], {})[tombstone["uuid"]] = _parse_datetime(
            tombstone["deleted_at"]
        )

    for table in reversed(snapshot_sync._model_import_order(models)):
        deletions = by_table.get(table)
        if not deletions:
            continue
        model = models[table]
        records = model.query.filter(model.uuid.in_(deletions)).all()
        removable = [
            record.uuid
            for record in records
            if record.updated_at <= deletions[record.uuid]
        ]
        if removable:
            model.query.filter(model.uuid.in_(removable)).delete(synchronize_session=False)
            db.session.flush()
    db.session.commit()


def _save_sync_state(tombstones):
    set_setting("sync.github_tombstones", json.dumps(tombstones, separators=(",", ":")))
    set_setting("sync.github_last_sync_at", utcnow().isoformat())


def pull_snapshot():
    """Fusionne dans la base locale les données présentes sur la branche GitHub."""
    settings = _settings()
    if settings is None:
        return {"ok": False, "configured": False, "error": "Synchronisation GitHub non configurée."}
    snapshot, tombstones, _ = _read_snapshot(settings)
    if snapshot is None:
        return {"ok": True, "configured": True, "found": False}
    remote_tombstones = _merge_tombstones(tombstones)
    tombstones = _merge_tombstones(
        remote_tombstones, _stored_tombstones(), _find_local_deletions(snapshot)
    )
    result = snapshot_sync.apply_snapshot(snapshot)
    _apply_tombstones(tombstones)
    _save_sync_state(tombstones)
    set_setting("sync.last_snapshot_at", utcnow().isoformat())
    set_setting("sync.last_error", "")
    set_setting("sync.last_total", str(result["total"]))
    db.session.commit()
    return {
        "ok": True,
        "configured": True,
        "found": True,
        "result": result,
        "pending_push": tombstones != remote_tombstones,
    }


def sync_now():
    """Récupère, fusionne puis publie l'instantané complet des données métier."""
    try:
        settings = _settings()
        if settings is None:
            return {
                "ok": False,
                "configured": False,
                "error": "Synchronisation GitHub non configurée.",
            }
        for attempt in range(3):
            remote_snapshot, remote_tombstones, sha = _read_snapshot(settings)
            remote_tombstones = _merge_tombstones(remote_tombstones)
            tombstones = _merge_tombstones(
                remote_tombstones,
                _stored_tombstones(),
                _find_local_deletions(remote_snapshot) if remote_snapshot else [],
            )
            if remote_snapshot is not None:
                snapshot_sync.apply_snapshot(remote_snapshot)
            _apply_tombstones(tombstones)
            snapshot = snapshot_sync.build_snapshot()
            if (
                remote_snapshot is not None
                and _snapshots_equal(snapshot, remote_snapshot)
                and tombstones == remote_tombstones
            ):
                total = sum(len(rows) for rows in snapshot["tables"].values())
                _save_sync_state(tombstones)
                set_setting("sync.last_snapshot_at", utcnow().isoformat())
                set_setting("sync.last_error", "")
                set_setting("sync.last_total", str(total))
                db.session.commit()
                current_app.extensions["github_sync_error"] = ""
                current_app.extensions["github_sync_pending_push"] = False
                return {
                    "ok": True,
                    "configured": True,
                    "result": {"commit": None, "received": {"total": total}},
                }
            try:
                result = _write_snapshot(settings, snapshot, tombstones, sha)
                if not isinstance(result, dict) or not result.get("commit"):
                    raise RuntimeError("GitHub n'a pas confirmé l'enregistrement des données.")
                _save_sync_state(tombstones)
                set_setting("sync.last_snapshot_at", utcnow().isoformat())
                set_setting("sync.last_error", "")
                total = sum(len(rows) for rows in snapshot["tables"].values())
                set_setting("sync.last_total", str(total))
                db.session.commit()
                outcome = {
                    "ok": True,
                    "configured": True,
                    "result": {"commit": result["commit"], "received": {"total": total}},
                }
                current_app.extensions["github_sync_error"] = ""
                current_app.extensions["github_sync_pending_push"] = False
                return outcome
            except GitHubConflictError:
                if attempt == 2:
                    raise
        raise RuntimeError("Conflit GitHub persistant après trois tentatives.")
    except (
        OSError,
        RuntimeError,
        ValueError,
        SQLAlchemyError,
        urllib.error.URLError,
        snapshot_sync.SnapshotConflictError,
    ) as exc:
        db.session.rollback()
        set_setting("sync.last_error", str(exc)[:500])
        db.session.commit()
        current_app.extensions["github_sync_error"] = str(exc)
        return {"ok": False, "configured": True, "error": str(exc)}


def register_automatic_sync(app):
    """Actualise périodiquement depuis GitHub et republie après les écritures HTTP."""
    app.extensions["github_sync_lock"] = threading.Lock()
    app.extensions["github_sync_last_pull"] = 0.0
    app.extensions["github_sync_last_push_attempt"] = 0.0
    app.extensions["github_sync_error"] = ""
    app.extensions["github_sync_pending_push"] = False

    @app.before_request
    def pull_github_changes():
        if (
            not app.config.get("GITHUB_SYNC_ENABLED")
            or not app.config.get("GITHUB_SYNC_TOKEN")
            or not app.config.get("GITHUB_SYNC_REPOSITORY")
        ):
            return None
        if app.config.get("GITHUB_SYNC_SKIP_PULL", False):
            return None

        interval = max(5, int(app.config.get("GITHUB_SYNC_POLL_SECONDS", 30)))
        now = time.monotonic()
        lock = app.extensions["github_sync_lock"]
        with lock:
            if now - app.extensions["github_sync_last_pull"] < interval:
                return None
            try:
                outcome = pull_snapshot()
                app.extensions["github_sync_last_pull"] = time.monotonic()
                app.extensions["github_sync_error"] = outcome.get("error", "")
                if outcome.get("pending_push"):
                    app.extensions["github_sync_pending_push"] = True
            except (
                OSError,
                RuntimeError,
                ValueError,
                SQLAlchemyError,
                urllib.error.URLError,
                snapshot_sync.SnapshotConflictError,
            ) as exc:
                app.logger.exception("Échec de la lecture de l'instantané GitHub.")
                app.extensions["github_sync_last_pull"] = time.monotonic()
                app.extensions["github_sync_error"] = (
                    f"Lecture GitHub impossible; données locales conservées : {exc}"
                )[:500]
        return None

    @app.after_request
    def push_github_changes(response):
        read_only_request = request_method_is_read_only()
        should_push = (
            not read_only_request or app.extensions["github_sync_pending_push"]
        )
        if (
            not app.config.get("GITHUB_SYNC_ENABLED")
            or not app.config.get("GITHUB_SYNC_TOKEN")
            or not should_push
            or response.status_code >= 400
            or request.endpoint == "admin.sync_process"
        ):
            return response

        if (
            read_only_request
            and time.monotonic() - app.extensions["github_sync_last_push_attempt"]
            < max(5, int(app.config.get("GITHUB_SYNC_POLL_SECONDS", 30)))
        ):
            return response
        lock = app.extensions["github_sync_lock"]
        with lock:
            app.extensions["github_sync_last_push_attempt"] = time.monotonic()
            outcome = sync_now()
            app.extensions["github_sync_error"] = outcome.get("error", "")
            if not outcome.get("ok"):
                app.logger.error("Échec de la publication des données sur GitHub : %s", outcome["error"])
        return response


def request_method_is_read_only():
    return request.method not in {"POST", "PUT", "PATCH", "DELETE"}
