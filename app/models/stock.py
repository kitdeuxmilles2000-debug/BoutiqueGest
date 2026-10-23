"""Stock : mouvements, lots, inventaires."""
from decimal import Decimal

from app.extensions import db
from app.models.base import BaseModel


class MovementKind:
    RECEPTION = "reception"
    VENTE = "vente"
    RETOUR = "retour"
    TRANSFERT = "transfert"
    PERTE = "perte"
    PERTE_PEREMPTION = "perte_peremption"
    CORRECTION_INVENTAIRE = "correction_inventaire"
    AJUSTEMENT = "ajustement"


# Types qui augmentent le stock
IN_KINDS = {MovementKind.RECEPTION, MovementKind.RETOUR, MovementKind.AJUSTEMENT}
# Types qui diminuent le stock
OUT_KINDS = {MovementKind.VENTE, MovementKind.PERTE, MovementKind.PERTE_PEREMPTION, MovementKind.TRANSFERT}

MOVEMENT_LABELS = {
    MovementKind.RECEPTION: "Réception",
    MovementKind.VENTE: "Vente",
    MovementKind.RETOUR: "Retour",
    MovementKind.TRANSFERT: "Transfert",
    MovementKind.PERTE: "Perte / casse",
    MovementKind.PERTE_PEREMPTION: "Péremption",
    MovementKind.CORRECTION_INVENTAIRE: "Correction d'inventaire",
    MovementKind.AJUSTEMENT: "Ajustement",
}


class StockEntryStatus:
    EN_ATTENTE = "en_attente"
    VALIDEE = "validee"
    REJETEE = "rejetee"


STOCK_ENTRY_STATUS_LABELS = {
    StockEntryStatus.EN_ATTENTE: "En attente de validation",
    StockEntryStatus.VALIDEE: "Validée",
    StockEntryStatus.REJETEE: "Rejetée",
}


STOCK_ENTRY_STATUS_BADGES = {
    StockEntryStatus.EN_ATTENTE: "amber",
    StockEntryStatus.VALIDEE: "green",
    StockEntryStatus.REJETEE: "red",
}


class Batch(BaseModel):
    __tablename__ = "batches"

    product_id = db.Column(db.Integer, db.ForeignKey("products.id"), nullable=False, index=True)
    lot_number = db.Column(db.String(60))
    expiry_date = db.Column(db.Date)
    qty_remaining = db.Column(db.Numeric(18, 3), default=Decimal("0"), nullable=False)
    cost_unit = db.Column(db.Numeric(18, 2), default=Decimal("0"), nullable=False)
    active = db.Column(db.Boolean, default=True, nullable=False)

    product = db.relationship("Product")

    def __repr__(self):
        return f"<Batch {self.lot_number} {self.expiry_date}>"


class StockEntryRequest(BaseModel):
    """Demande d'entrée de stock en attente de validation par le propriétaire.

    L'entrée ne modifie pas le stock tant qu'elle n'est pas validée par le propriétaire
    après contrôle physique.
    """

    __tablename__ = "stock_entry_requests"

    reference = db.Column(db.String(40), unique=True, nullable=False, index=True)
    product_id = db.Column(db.Integer, db.ForeignKey("products.id"), nullable=False, index=True)
    currency = db.Column(db.String(3), default="CDF", nullable=False)
    status = db.Column(db.String(20), default=StockEntryStatus.EN_ATTENTE, nullable=False, index=True)

    quantity = db.Column(db.Numeric(18, 3), nullable=False)
    unit_id = db.Column(db.Integer, db.ForeignKey("units.id"))
    qty_base = db.Column(db.Numeric(18, 3), nullable=False)
    cost_unit = db.Column(db.Numeric(18, 2), nullable=False)
    reason = db.Column(db.String(255))
    notes = db.Column(db.Text)

    lot_number = db.Column(db.String(60))
    expiry_date = db.Column(db.Date)

    supplier_id = db.Column(db.Integer, db.ForeignKey("suppliers.id"))
    purchase_id = db.Column(db.Integer, db.ForeignKey("purchases.id"))

    created_by_id = db.Column(db.Integer, db.ForeignKey("users.id"))
    validated_by_id = db.Column(db.Integer, db.ForeignKey("users.id"))
    rejected_by_id = db.Column(db.Integer, db.ForeignKey("users.id"))
    validated_at = db.Column(db.DateTime)
    rejected_at = db.Column(db.DateTime)
    reject_reason = db.Column(db.String(255))

    product = db.relationship("Product")
    unit = db.relationship("Unit")
    supplier = db.relationship("Supplier")
    purchase = db.relationship("Purchase")
    created_by = db.relationship("User", foreign_keys=[created_by_id])
    validated_by = db.relationship("User", foreign_keys=[validated_by_id])
    rejected_by = db.relationship("User", foreign_keys=[rejected_by_id])

    def __repr__(self):
        return f"<StockEntryRequest {self.reference} {self.status}>"


class StockMovement(BaseModel):
    __tablename__ = "stock_movements"

    product_id = db.Column(db.Integer, db.ForeignKey("products.id"), nullable=False, index=True)
    kind = db.Column(db.String(30), nullable=False, index=True)
    quantity = db.Column(db.Numeric(18, 3), nullable=False)  # signe, en unite de base
    unit_id = db.Column(db.Integer, db.ForeignKey("units.id"))
    unit_factor = db.Column(db.Numeric(18, 4), default=Decimal("1"))
    cost_unit = db.Column(db.Numeric(18, 2))
    currency = db.Column(db.String(3), default="CDF", nullable=False)

    source_type = db.Column(db.String(40))
    source_uuid = db.Column(db.String(36), index=True)
    reason = db.Column(db.String(255))
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"))
    batch_id = db.Column(db.Integer, db.ForeignKey("batches.id"))
    stock_entry_request_id = db.Column(db.Integer, db.ForeignKey("stock_entry_requests.id"))

    product = db.relationship("Product")
    unit = db.relationship("Unit")
    user = db.relationship("User")
    batch = db.relationship("Batch")
    stock_entry_request = db.relationship("StockEntryRequest")

    def signed_quantity_for_display(self):
        return self.quantity

    def __repr__(self):
        return f"<StockMovement {self.kind} {self.quantity}>"


class InventoryStatus:
    OPEN = "ouverte"
    SUBMITTED = "soumise"
    VALIDATED = "validee"


class InventorySession(BaseModel):
    __tablename__ = "inventory_sessions"

    reference = db.Column(db.String(40), unique=True, nullable=False)
    scope = db.Column(db.String(120))
    status = db.Column(db.String(20), default=InventoryStatus.OPEN, nullable=False)
    responsable_id = db.Column(db.Integer, db.ForeignKey("users.id"))
    validated_by_id = db.Column(db.Integer, db.ForeignKey("users.id"))
    validated_at = db.Column(db.DateTime)
    notes = db.Column(db.Text)

    responsable = db.relationship("User", foreign_keys=[responsable_id])
    validated_by = db.relationship("User", foreign_keys=[validated_by_id])
    lines = db.relationship(
        "InventoryLine",
        back_populates="session",
        cascade="all, delete-orphan",
    )

    @property
    def has_gaps(self):
        return any((line.ecart or 0) != 0 for line in self.lines)

    def __repr__(self):
        return f"<InventorySession {self.reference}>"


class InventoryLine(BaseModel):
    __tablename__ = "inventory_lines"

    session_id = db.Column(db.Integer, db.ForeignKey("inventory_sessions.id"), nullable=False)
    product_id = db.Column(db.Integer, db.ForeignKey("products.id"), nullable=False)
    qty_theorique = db.Column(db.Numeric(18, 3), default=Decimal("0"), nullable=False)
    qty_comptee = db.Column(db.Numeric(18, 3), default=Decimal("0"), nullable=False)
    ecart = db.Column(db.Numeric(18, 3), default=Decimal("0"), nullable=False)
    ecart_valeur = db.Column(db.Numeric(18, 2), default=Decimal("0"), nullable=False)
    reason = db.Column(db.String(255))

    session = db.relationship("InventorySession", back_populates="lines")
    product = db.relationship("Product")
