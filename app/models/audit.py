"""Journal d'audit (append-only) des operations sensibles.

Ce journal ne doit jamais etre modifie ni supprime par l'application.
"""
from app.extensions import db
from app.models.base import new_uuid, utcnow


class AuditLog(db.Model):
    __tablename__ = "audit_logs"

    id = db.Column(db.Integer, primary_key=True)
    uuid = db.Column(db.String(36), unique=True, nullable=False, default=new_uuid, index=True)
    at = db.Column(db.DateTime, default=utcnow, nullable=False, index=True)

    user_id = db.Column(db.Integer, db.ForeignKey("users.id"))
    username = db.Column(db.String(60))
    action = db.Column(db.String(60), nullable=False, index=True)
    entity = db.Column(db.String(80), index=True)
    entity_uuid = db.Column(db.String(36), index=True)

    device_id = db.Column(db.String(80))
    ip = db.Column(db.String(45))

    value_before = db.Column(db.Text)
    value_after = db.Column(db.Text)
    reason = db.Column(db.String(255))
    approver_id = db.Column(db.Integer, db.ForeignKey("users.id"))

    def __repr__(self):
        return f"<AuditLog {self.action} {self.entity}@{self.at}>"
