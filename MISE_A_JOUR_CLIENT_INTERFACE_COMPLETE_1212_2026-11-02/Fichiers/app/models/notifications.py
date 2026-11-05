"""Notifications / Alertes centralisées."""
from app.extensions import db
from app.models.base import BaseModel


class NotificationType:
    CREDIT_ECHU = "credit_echu"
    CREDIT_JOUR = "credit_jour"
    STOCK_BAS = "stock_bas"
    STOCK_RUPTURE = "stock_rupture"
    STOCK_REPLENISHED = "stock_replenis"
    DEBT_PAID = "debt_paid"
    PASSWORD_CHANGED = "password_changed"
    GENERALE = "generale"


NOTIFICATION_TYPE_LABELS = {
    NotificationType.CREDIT_ECHU: "Crédit échue",
    NotificationType.CREDIT_JOUR: "Échéance du jour",
    NotificationType.STOCK_BAS: "Stock bas",
    NotificationType.STOCK_RUPTURE: "Rupture de stock",
    NotificationType.STOCK_REPLENISHED: "Stock remis à niveau",
    NotificationType.DEBT_PAID: "Dette payée",
    NotificationType.PASSWORD_CHANGED: "Sécurité",
    NotificationType.GENERALE: "Générale",
}

# Badge couleur par type (cohérent avec la palette app.css)
NOTIFICATION_TYPE_BADGES = {
    NotificationType.CREDIT_ECHU: "red",
    NotificationType.CREDIT_JOUR: "amber",
    NotificationType.STOCK_BAS: "amber",
    NotificationType.STOCK_RUPTURE: "red",
    NotificationType.STOCK_REPLENISHED: "green",
    NotificationType.DEBT_PAID: "green",
    NotificationType.PASSWORD_CHANGED: "blue",
    NotificationType.GENERALE: "gray",
}


class Notification(BaseModel):
    __tablename__ = "notifications"

    type = db.Column(db.String(30), nullable=False, index=True)
    title = db.Column(db.String(160), nullable=False)
    message = db.Column(db.Text, nullable=False)
    link = db.Column(db.String(255))
    priority = db.Column(db.Integer, default=0, nullable=False)
    read = db.Column(db.Boolean, default=False, nullable=False, index=True)
    dismissed = db.Column(db.Boolean, default=False, nullable=False, index=True)
    entity_type = db.Column(db.String(40))
    entity_id = db.Column(db.Integer)
    entity_uuid = db.Column(db.String(36))

    def __repr__(self):
        return f"<Notification {self.type} {self.title}>"
