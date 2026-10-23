"""Socle commun des modeles : identifiant, UUID de synchronisation, horodatage."""
import uuid as _uuid
from datetime import datetime, timezone

from app.extensions import db


def utcnow():
    """Date/heure UTC naive (coherente avec SQLite et les comparaisons)."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


def new_uuid():
    return str(_uuid.uuid4())


class BaseModel(db.Model):
    """Modele abstrait : id, uuid (cle de synchronisation), created/updated."""

    __abstract__ = True

    id = db.Column(db.Integer, primary_key=True)
    uuid = db.Column(db.String(36), unique=True, nullable=False, default=new_uuid, index=True)
    created_at = db.Column(db.DateTime, default=utcnow, nullable=False)
    updated_at = db.Column(db.DateTime, default=utcnow, onupdate=utcnow, nullable=False)

    def to_dict(self):
        data = {}
        for col in self.__table__.columns:
            value = getattr(self, col.name)
            if isinstance(value, datetime):
                value = value.isoformat()
            data[col.name] = value
        return data

    def __repr__(self):
        return f"<{self.__class__.__name__} id={self.id}>"
