"""Synchronisation unidirectionnelle de la base locale vers Render."""
import json
import secrets
import urllib.error
import urllib.request
from datetime import date, datetime
from decimal import Decimal

from flask import current_app
from sqlalchemy import Date, DateTime, Numeric
from sqlalchemy.exc import IntegrityError

from app.extensions import db
from app.models import User
from app.models.base import utcnow
from app.models.user import get_setting, set_setting

SNAPSHOT_TABLES = frozenset(
    {
        "batches",
        "cash_movements",
        "cash_registers",
        "cash_sessions",
        "categories",
        "credits",
        "customers",
        "exchange_rates",
        "expense_categories",
        "expenses",
        "installments",
        "inventory_lines",
        "inventory_sessions",
        "payments",
        "price_history",
        "product_units",
        "products",
        "purchase_lines",
        "purchases",
        "refunds",
        "sale_lines",
        "sales",
        "settlements",
        "stock_entry_requests",
        "stock_movements",
        "suppliers",
        "units",
    }
)
NATURAL_KEY_COLUMNS = {
    "cash_registers": ("name",),
    "categories": ("name",),
    "expense_categories": ("name",),
    "units": ("code",),
}
NATURAL_KEY_GUARDS = {
    "cash_registers": ("currency",),
    "units": ("kind",),
}


class SnapshotConflictError(Exception):
    """Unicite métier déjà prise par un autre enregistrement sur Render."""


def _models_by_table():
    return {
        mapper.local_table.name: mapper.class_
        for mapper in db.Model.registry.mappers
        if mapper.local_table.name in SNAPSHOT_TABLES
    }


def _json_value(value):
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return str(value)
    return value


def build_snapshot():
    """Construit un instantané métier sans exporter les secrets d'authentification."""
    models = _models_by_table()
    if set(models) != SNAPSHOT_TABLES:
        missing = sorted(SNAPSHOT_TABLES - set(models))
        raise RuntimeError(f"Modèles de synchronisation absents : {', '.join(missing)}")

    tables = {}
    for table_name in sorted(SNAPSHOT_TABLES):
        model = models[table_name]
        tables[table_name] = [
            {column.name: _json_value(getattr(record, column.name)) for column in model.__table__.columns}
            for record in model.query.order_by(model.id).all()
        ]

    users = [
        {"id": user.id, "uuid": user.uuid, "full_name": user.full_name}
        for user in User.query.order_by(User.id).all()
    ]
    return {"version": 1, "users": users, "tables": tables}


def _model_import_order(models):
    dependencies = {table: set() for table in models}
    for table_name, model in models.items():
        for column in model.__table__.columns:
            if not column.nullable:
                for foreign_key in column.foreign_keys:
                    target = foreign_key.column.table.name
                    if target in models and target != table_name:
                        dependencies[table_name].add(target)

    ordered = []
    while dependencies:
        ready = sorted(table for table, refs in dependencies.items() if not refs)
        if not ready:
            raise RuntimeError("Dépendance circulaire non nullable dans le schéma synchronisé.")
        ordered.extend(ready)
        for table in ready:
            dependencies.pop(table)
        for refs in dependencies.values():
            refs.difference_update(ready)
    return ordered


def _validate_snapshot(snapshot, models):
    if not isinstance(snapshot, dict) or snapshot.get("version") != 1:
        raise ValueError("Version de synchronisation absente ou non prise en charge.")
    if not isinstance(snapshot.get("users"), list):
        raise ValueError("La liste des utilisateurs source est invalide.")
    tables = snapshot.get("tables")
    if not isinstance(tables, dict) or set(tables) != SNAPSHOT_TABLES:
        raise ValueError("L'instantané doit contenir exactement les tables métier attendues.")

    seen_user_ids = set()
    seen_user_uuids = set()
    for user in snapshot["users"]:
        if (
            not isinstance(user, dict)
            or set(user) != {"id", "uuid", "full_name"}
            or not isinstance(user.get("id"), int)
            or not isinstance(user.get("uuid"), str)
            or not isinstance(user.get("full_name"), str)
        ):
            raise ValueError("Une identité utilisateur de l'instantané est invalide.")
        if user["id"] in seen_user_ids or user["uuid"] in seen_user_uuids:
            raise ValueError("Identité utilisateur en double dans l'instantané.")
        seen_user_ids.add(user["id"])
        seen_user_uuids.add(user["uuid"])

    for table_name, rows in tables.items():
        if not isinstance(rows, list):
            raise ValueError(f"La table {table_name} doit être une liste.")
        allowed_columns = {column.name for column in models[table_name].__table__.columns}
        seen_uuids = set()
        for row in rows:
            if not isinstance(row, dict) or set(row) != allowed_columns:
                raise ValueError(
                    f"Une ligne de la table {table_name} contient des champs manquants ou inconnus."
                )
            if not isinstance(row.get("id"), int) or not isinstance(row.get("uuid"), str):
                raise ValueError(f"Une ligne de la table {table_name} n'a pas d'identifiant valide.")
            if row["uuid"] in seen_uuids:
                raise ValueError(f"UUID en double dans la table {table_name}.")
            seen_uuids.add(row["uuid"])


def _source_user_map(users):
    mapped = {}
    for source in users:
        username = f"sync_{source['uuid'].replace('-', '')}"
        user = User.query.filter_by(username=username).first()
        if user is None:
            user = User(username=username, full_name=source["full_name"][:120], active=False)
            user.set_password(_new_random_password())
            db.session.add(user)
            db.session.flush()
        else:
            user.full_name = source["full_name"][:120]
            user.active = False
        mapped[source["id"]] = user.id
    return mapped


def _new_random_password():
    return secrets.token_urlsafe(48)


def _convert_value(column, value):
    if value is None:
        return None
    if isinstance(column.type, DateTime):
        return datetime.fromisoformat(value) if isinstance(value, str) else value
    if isinstance(column.type, Date):
        return date.fromisoformat(value) if isinstance(value, str) else value
    if isinstance(column.type, Numeric):
        return Decimal(str(value))
    return value


def _mapped_foreign_value(column, source_value, user_ids, id_maps):
    if source_value is None:
        return None
    target_table = next(iter(column.foreign_keys)).column.table.name
    if target_table == "users":
        return user_ids.get(source_value)
    return id_maps.get(target_table, {}).get(source_value)


def apply_snapshot(snapshot):
    """Fusionne atomiquement les enregistrements par UUID sans supprimer Render."""
    models = _models_by_table()
    _validate_snapshot(snapshot, models)

    user_ids = _source_user_map(snapshot["users"])
    id_maps = {"users": user_ids}
    counts = {}

    try:
        for table_name in _model_import_order(models):
            model = models[table_name]
            rows = snapshot["tables"][table_name]
            id_maps[table_name] = {}
            existing = {}
            for start in range(0, len(rows), 500):
                uuids = [item["uuid"] for item in rows[start : start + 500]]
                existing.update(
                    {
                        row.uuid: row
                        for row in model.query.filter(model.uuid.in_(uuids)).all()
                    }
                )

            for row in rows:
                record = existing.get(row["uuid"])
                if record is None:
                    natural_columns = NATURAL_KEY_COLUMNS.get(table_name, ())
                    if natural_columns:
                        natural_values = {name: row[name] for name in natural_columns}
                        record = model.query.filter_by(**natural_values).first()
                        if record is not None:
                            guards = NATURAL_KEY_GUARDS.get(table_name, ())
                            if any(getattr(record, name) != row[name] for name in guards):
                                raise SnapshotConflictError(
                                    f"Conflit de référentiel sur {table_name}; aucune donnée "
                                    "n'a été modifiée."
                                )
                    if record is None:
                        record = model()
                        record.uuid = row["uuid"]
                        db.session.add(record)

                id_maps[table_name][row["id"]] = record.id
                for column in model.__table__.columns:
                    name = column.name
                    if name in {"id", "uuid"} or name not in row:
                        continue
                    value = row[name]
                    if column.foreign_keys:
                        value = _mapped_foreign_value(column, value, user_ids, id_maps)
                        if value is None and not column.nullable:
                            raise ValueError(
                                f"Référence manquante dans {table_name}.{name}; "
                                "l'instantané local est incomplet."
                            )
                    setattr(record, name, _convert_value(column, value))
                db.session.flush()
                id_maps[table_name][row["id"]] = record.id

            counts[table_name] = len(rows)

        for table_name, model in models.items():
            row_by_id = {row["id"]: row for row in snapshot["tables"][table_name]}
            for source_id, target_id in id_maps[table_name].items():
                record = db.session.get(model, target_id)
                source = row_by_id[source_id]
                for column in model.__table__.columns:
                    if not column.foreign_keys or column.name not in source:
                        continue
                    value = _mapped_foreign_value(column, source[column.name], user_ids, id_maps)
                    if value is None and source[column.name] is not None and not column.nullable:
                        raise ValueError(
                            f"Référence manquante dans {table_name}.{column.name}; "
                            "l'instantané local est incomplet."
                        )
                    setattr(record, column.name, value)
        db.session.flush()
        db.session.commit()
    except IntegrityError as exc:
        db.session.rollback()
        raise SnapshotConflictError(
            "Collision avec une donnée Render existante. Aucune modification de cet import "
            "n'a été conservée; vérifiez les codes et références en double."
        ) from exc
    except Exception:
        db.session.rollback()
        raise

    return {"users": len(snapshot["users"]), "tables": counts, "total": sum(counts.values())}


def _sender():
    url = current_app.config.get("SYNC_REMOTE_URL", "").strip()
    token = current_app.config.get("SYNC_API_TOKEN", "").strip()
    if not current_app.config.get("SYNC_ENABLED") or not url or not token:
        return None
    if not url.startswith("https://"):
        raise ValueError("L'URL de synchronisation doit utiliser HTTPS.")

    def send(snapshot):
        import gzip

        body = gzip.compress(json.dumps(snapshot, ensure_ascii=False, separators=(",", ":")).encode("utf-8"))
        request = urllib.request.Request(
            url,
            data=body,
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
                "Content-Encoding": "gzip",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=90) as response:
                response_data = response.read(1024 * 1024)
                result = json.loads(response_data.decode("utf-8"))
                if (
                    response.status != 200
                    or not isinstance(result, dict)
                    or not result.get("ok")
                    or not isinstance(result.get("received"), dict)
                    or not isinstance(result["received"].get("total"), int)
                ):
                    raise RuntimeError("Le serveur Render n'a pas confirmé la synchronisation.")
                return result
        except urllib.error.HTTPError as exc:
            details = exc.read(4096).decode("utf-8", errors="replace")
            try:
                message = json.loads(details).get("error", details)
            except json.JSONDecodeError:
                message = details
            raise RuntimeError(f"Réponse Render {exc.code} : {message}") from exc

    return send


def sync_now():
    """Envoie un instantané complet; les événements historiques restent locaux."""
    try:
        sender = _sender()
        if sender is None:
            return {"ok": False, "configured": False, "error": "Synchronisation distante non configurée."}

        result = sender(build_snapshot())
        set_setting("sync.last_snapshot_at", utcnow().isoformat())
        set_setting("sync.last_error", "")
        set_setting("sync.last_total", str(result.get("received", {}).get("total", 0)))
        db.session.commit()
        return {"ok": True, "configured": True, "result": result}
    except (OSError, RuntimeError, ValueError, urllib.error.URLError) as exc:
        db.session.rollback()
        set_setting("sync.last_error", str(exc)[:500])
        db.session.commit()
        return {"ok": False, "configured": True, "error": str(exc)}


def stats():
    last_snapshot = get_setting("sync.last_snapshot_at")
    last_error = get_setting("sync.last_error")
    last_total = get_setting("sync.last_total", "0")
    try:
        last_snapshot = datetime.fromisoformat(last_snapshot) if last_snapshot else None
    except ValueError:
        last_snapshot = None
    try:
        last_total = int(last_total)
    except (TypeError, ValueError):
        last_total = 0

    configured = bool(
        current_app.config.get("SYNC_ENABLED")
        and current_app.config.get("SYNC_REMOTE_URL")
        and current_app.config.get("SYNC_API_TOKEN")
    )
    return {
        "configured": configured,
        "receiver_configured": bool(current_app.config.get("SYNC_API_TOKEN")),
        "last_snapshot_at": last_snapshot,
        "last_error": last_error,
        "last_total": last_total,
    }
