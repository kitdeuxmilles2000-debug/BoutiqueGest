"""Evenements de synchronisation (file d'attente locale, idempotente).

Chaque operation metier sensible cree un SyncEvent portant un UUID unique.
Le serveur distant detecte les doublons par UUID : rejouer un evenement
deja acquitte ne cree rien de nouveau (idempotence par cle d'idempotence).

Le serveur local reste la reference ; la sync ne conditionne jamais une vente.
"""
from app.extensions import db
from app.models.base import BaseModel, utcnow


class SyncStatus:
    EN_ATTENTE = "a_envoyer"
    ENVOYE = "envoye"
    ACQUITTE = "acquitte"
    ERREUR = "erreur"


SYNC_STATUS_LABELS = {
    SyncStatus.EN_ATTENTE: "A envoyer",
    SyncStatus.ENVOYE: "Envoye",
    SyncStatus.ACQUITTE: "Acquitte",
    SyncStatus.ERREUR: "Erreur",
}

SYNC_STATUS_BADGES = {
    SyncStatus.EN_ATTENTE: "amber",
    SyncStatus.ENVOYE: "blue",
    SyncStatus.ACQUITTE: "green",
    SyncStatus.ERREUR: "rouge",
}


class SyncEvent(BaseModel):
    __tablename__ = "sync_events"

    # Cle d'idempotence : identifie l'entite et l'operation (unique cote serveur).
    idempotency_key = db.Column(db.String(120), unique=True, nullable=False, index=True)
    entity = db.Column(db.String(80), nullable=False, index=True)
    entity_uuid = db.Column(db.String(36), index=True)
    action = db.Column(db.String(40), nullable=False)

    payload = db.Column(db.Text)
    device_id = db.Column(db.String(80))
    author_id = db.Column(db.Integer, db.ForeignKey("users.id"))

    status = db.Column(db.String(20), default=SyncStatus.EN_ATTENTE, nullable=False, index=True)
    attempts = db.Column(db.Integer, default=0, nullable=False)
    last_error = db.Column(db.String(255))
    sent_at = db.Column(db.DateTime)
    ack_at = db.Column(db.DateTime)

    def mark_sent(self):
        self.status = SyncStatus.ENVOYE
        self.attempts = (self.attempts or 0) + 1
        self.sent_at = utcnow()
        self.last_error = None

    def mark_ack(self):
        self.status = SyncStatus.ACQUITTE
        self.ack_at = utcnow()
        self.last_error = None

    def mark_error(self, message):
        self.status = SyncStatus.ERREUR
        self.attempts = (self.attempts or 0) + 1
        self.last_error = (message or "")[:255]

    def __repr__(self):
        return f"<SyncEvent {self.entity}:{self.action} {self.status}>"


def enqueue(entity, action, entity_uuid=None, payload=None, author_id=None, device_id=None):
    """Met un evenement en file (ou retourne celui deja present : idempotence locale)."""
    key = f"{entity}:{entity_uuid or '-'}:{action}"
    existing = SyncEvent.query.filter_by(idempotency_key=key).first()
    if existing:
        return existing, False
    event = SyncEvent(
        idempotency_key=key,
        entity=entity,
        entity_uuid=entity_uuid,
        action=action,
        payload=payload,
        author_id=author_id,
        device_id=device_id,
        status=SyncStatus.EN_ATTENTE,
    )
    db.session.add(event)
    return event, True
