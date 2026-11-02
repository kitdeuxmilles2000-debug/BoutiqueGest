"""API privée de réception des instantanés métier locaux."""
import gzip
import hmac
import io
import json

from flask import Blueprint, Response, current_app, jsonify, request
from sqlalchemy.exc import SQLAlchemyError

from app.extensions import csrf, db
from app.services.sync import SnapshotConflictError, apply_snapshot, build_snapshot

sync_api_bp = Blueprint("sync_api", __name__, url_prefix="/api/sync")
MAX_COMPRESSED_BYTES = 25 * 1024 * 1024
MAX_UNCOMPRESSED_BYTES = 100 * 1024 * 1024


def _authorization_error():
    expected_token = current_app.config.get("SYNC_API_TOKEN", "").strip()
    if not expected_token:
        return jsonify(ok=False, error="Réception de synchronisation non configurée."), 503

    authorization = request.headers.get("Authorization", "")
    supplied_token = authorization.removeprefix("Bearer ").strip()
    if not authorization.startswith("Bearer ") or not hmac.compare_digest(
        supplied_token, expected_token
    ):
        return jsonify(ok=False, error="Authentification invalide."), 401
    return None


@sync_api_bp.get("/snapshot")
@csrf.exempt
def send_snapshot():
    auth_error = _authorization_error()
    if auth_error:
        return auth_error

    content = json.dumps(
        {"ok": True, "snapshot": build_snapshot()},
        ensure_ascii=False,
        separators=(",", ":"),
    ).encode("utf-8")
    if len(content) > MAX_UNCOMPRESSED_BYTES:
        return jsonify(ok=False, error="Instantané décompressé trop volumineux."), 413

    compressed = gzip.compress(content)
    if len(compressed) > MAX_COMPRESSED_BYTES:
        return jsonify(ok=False, error="Instantané compressé trop volumineux."), 413
    return Response(
        compressed,
        status=200,
        headers={
            "Content-Type": "application/json",
            "Content-Encoding": "gzip",
            "Cache-Control": "no-store",
        },
    )


@sync_api_bp.post("/snapshot")
@csrf.exempt
def receive_snapshot():
    auth_error = _authorization_error()
    if auth_error:
        return auth_error

    if request.headers.get("Content-Encoding", "").lower() != "gzip":
        return jsonify(ok=False, error="Le contenu doit être compressé avec gzip."), 415
    if request.content_length is not None and request.content_length > MAX_COMPRESSED_BYTES:
        return jsonify(ok=False, error="Instantané compressé trop volumineux."), 413

    try:
        compressed = request.stream.read(MAX_COMPRESSED_BYTES + 1)
        if len(compressed) > MAX_COMPRESSED_BYTES:
            return jsonify(ok=False, error="Instantané compressé trop volumineux."), 413
        with gzip.GzipFile(fileobj=io.BytesIO(compressed)) as stream:
            content = stream.read(MAX_UNCOMPRESSED_BYTES + 1)
        if len(content) > MAX_UNCOMPRESSED_BYTES:
            return jsonify(ok=False, error="Instantané décompressé trop volumineux."), 413
        snapshot = json.loads(content.decode("utf-8"))
    except (OSError, EOFError, UnicodeDecodeError, json.JSONDecodeError):
        return jsonify(ok=False, error="Instantané gzip/JSON invalide."), 400

    try:
        result = apply_snapshot(snapshot)
    except ValueError as exc:
        return jsonify(ok=False, error=str(exc)), 400
    except SnapshotConflictError as exc:
        return jsonify(ok=False, error=str(exc)), 409
    except SQLAlchemyError:
        db.session.rollback()
        current_app.logger.exception("Échec de l'import de l'instantané distant.")
        return jsonify(ok=False, error="Erreur de base de données; l'import a été annulé."), 500

    return jsonify(ok=True, received=result), 200
