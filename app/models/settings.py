"""Parametres metier : taux de change (manuel, historise) et file d'e-mails.

Le taux de change (decisions CDC #9) est saisi **manuellement** (1x/jour),
**historise** et **jamais recalcule en silence**. Aucun montant n'est converti
automatiquement : le taux sert a l'affichage et aux vues consolidees.

La file d'e-mails (decision #11) permet d'envoyer le rapport journalier au
proprietaire apres cloture validee : envoye si un serveur SMTP est configure,
sinon **mis en attente** et consultable.
"""
from decimal import Decimal

from app.extensions import db
from app.models.base import BaseModel, utcnow


class ExchangeRate(BaseModel):
    """Taux de change USD -> CDF, saisi manuellement, avec historique."""

    __tablename__ = "exchange_rates"

    base_currency = db.Column(db.String(3), default="USD", nullable=False)
    quote_currency = db.Column(db.String(3), default="CDF", nullable=False)
    rate = db.Column(db.Numeric(18, 6), nullable=False)
    effective_date = db.Column(db.Date, nullable=False, index=True)
    source = db.Column(db.String(120))
    notes = db.Column(db.Text)
    created_by_id = db.Column(db.Integer, db.ForeignKey("users.id"))

    created_by = db.relationship("User")

    def __repr__(self):
        return f"<ExchangeRate {self.base_currency}->{self.quote_currency}={self.rate} @{self.effective_date}>"


class OutboxStatus:
    EN_ATTENTE = "en_attente"
    ENVOYE = "envoye"
    ERREUR = "erreur"


OUTBOX_STATUS_LABELS = {
    OutboxStatus.EN_ATTENTE: "En attente",
    OutboxStatus.ENVOYE: "Envoye",
    OutboxStatus.ERREUR: "Erreur",
}

OUTBOX_STATUS_BADGES = {
    OutboxStatus.EN_ATTENTE: "amber",
    OutboxStatus.ENVOYE: "green",
    OutboxStatus.ERREUR: "rouge",
}


class OutboxMessage(BaseModel):
    """Message a envoyer (rapport, alerte). En attente si SMTP non configure."""

    __tablename__ = "outbox_messages"

    to_address = db.Column(db.String(255), nullable=False, index=True)
    subject = db.Column(db.String(255), nullable=False)
    body = db.Column(db.Text, nullable=False)
    kind = db.Column(db.String(40), default="rapport", nullable=False)

    status = db.Column(db.String(20), default=OutboxStatus.EN_ATTENTE, nullable=False, index=True)
    attempts = db.Column(db.Integer, default=0, nullable=False)
    last_error = db.Column(db.String(255))
    sent_at = db.Column(db.DateTime)
    created_by_id = db.Column(db.Integer, db.ForeignKey("users.id"))

    created_by = db.relationship("User")

    def __repr__(self):
        return f"<OutboxMessage {self.subject} {self.status}>"
