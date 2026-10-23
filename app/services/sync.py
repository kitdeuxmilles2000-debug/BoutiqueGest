"""Service de synchronisation distante (idempotente).

Le serveur local est la reference. Les operations sensibles sont mises en file
(voir app.models.sync) puis envoyees au serveur distant des qu'Internet est
disponible. Le serveur distant detecte les doublons par cle d'idempotence :
rejouer un evenement deja acquitte ne cree rien.

Sans serveur distant configure, la file reste locale : la boutique continue de
fonctionner (ventes, caisse, stock) sans Internet.
"""
import json

from flask import current_app

from app.extensions import db
from app.models.sync import SYNC_STATUS_LABELS, SyncEvent, SyncStatus, enqueue as _enqueue


def enqueue(*args, **kwargs):
    return _enqueue(*args, **kwargs)


def _sender():
    """Fonction d'envoi : None si la sync distante n'est pas configuree."""
    url = current_app.config.get("SYNC_REMOTE_URL")
    if not current_app.config.get("SYNC_ENABLED") or not url:
        return None

    def send(event):
        # Envoi HTTP reel a brancher sur l'API distante (POST /sync).
        import urllib.request

        body = json.dumps(
            {
                "idempotency_key": event.idempotency_key,
                "entity": event.entity,
                "entity_uuid": event.entity_uuid,
                "action": event.action,
                "payload": event.payload,
            }
        ).encode("utf-8")
        req = urllib.request.Request(
            url, data=body, headers={"Content-Type": "application/json"}, method="POST"
        )
        with urllib.request.urlopen(req, timeout=10) as resp:  # noqa: S310
            return resp.status == 200

    return send


def process_queue(limit=50):
    """Envoie les evenements en attente/erreur. Retourne un bilan."""
    sender = _sender()
    pending = (
        SyncEvent.query.filter(SyncEvent.status.in_([SyncStatus.EN_ATTENTE, SyncStatus.ERREUR]))
        .order_by(SyncEvent.created_at)
        .limit(limit)
        .all()
    )
    bilan = {"traites": 0, "acquittes": 0, "erreurs": 0, "en_attente": 0}
    if sender is None:
        bilan["en_attente"] = len(pending)
        return bilan

    for event in pending:
        bilan["traites"] += 1
        try:
            event.mark_sent()
            if sender(event):
                event.mark_ack()
                bilan["acquittes"] += 1
        except Exception as exc:  # noqa: BLE001
            event.mark_error(str(exc))
            bilan["erreurs"] += 1
    db.session.commit()
    return bilan


def ingest(payload):
    """Reception (cote distant) d'un evenement. Idempotent par cle.

    Retourne (created, event). Si la cle existe deja, rien n'est recree.
    """
    key = payload.get("idempotency_key")
    existing = SyncEvent.query.filter_by(idempotency_key=key).first()
    if existing is not None:
        if existing.status != SyncStatus.ACQUITTE:
            existing.mark_ack()
            db.session.commit()
        return False, existing

    event = SyncEvent(
        idempotency_key=key,
        entity=payload.get("entity"),
        entity_uuid=payload.get("entity_uuid"),
        action=payload.get("action"),
        payload=payload.get("payload"),
        status=SyncStatus.ACQUITTE,
    )
    db.session.add(event)
    db.session.commit()
    return True, event


def stats():
    """Etat de la file : compteurs par statut + derniere synchronisation."""
    counts = {status: SyncEvent.query.filter_by(status=status).count() for status in SYNC_STATUS_LABELS}
    last_ack = (
        SyncEvent.query.filter(SyncEvent.ack_at.isnot(None))
        .order_by(SyncEvent.ack_at.desc())
        .first()
    )
    return {
        "counts": counts,
        "labels": SYNC_STATUS_LABELS,
        "pending": counts.get(SyncStatus.EN_ATTENTE, 0) + counts.get(SyncStatus.ERREUR, 0),
        "last_ack_at": last_ack.ack_at if last_ack else None,
        "total": sum(counts.values()),
    }
