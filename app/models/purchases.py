"""Achats et receptions : commandes fournisseurs et entree en stock.

Un achat est **mono-devise** (comme une vente). Il suit un cycle :
brouillon -> commande -> receptionnee (validation). La validation cree les
mouvements de stock (reception) et, si la commande est a credit, une dette
fournisseur. Une commande receptionnee est immuable : on la corrige par
contre-ecriture (annulation tracee), jamais par modification directe.
"""
from decimal import Decimal

from app.extensions import db
from app.models.base import BaseModel, utcnow


class PurchaseStatus:
    BROUILLON = "brouillon"
    COMMANDE = "commande"
    RECEPTIONNEE = "receptionnee"
    ANNULEE = "annulee"


PURCHASE_STATUS_LABELS = {
    PurchaseStatus.BROUILLON: "Brouillon",
    PurchaseStatus.COMMANDE: "Commandee",
    PurchaseStatus.RECEPTIONNEE: "Receptionnee",
    PurchaseStatus.ANNULEE: "Annulee",
}

PURCHASE_STATUS_BADGES = {
    PurchaseStatus.BROUILLON: "gray",
    PurchaseStatus.COMMANDE: "amber",
    PurchaseStatus.RECEPTIONNEE: "green",
    PurchaseStatus.ANNULEE: "rouge",
}


class Purchase(BaseModel):
    __tablename__ = "purchases"

    reference = db.Column(db.String(40), unique=True, nullable=False, index=True)
    supplier_id = db.Column(db.Integer, db.ForeignKey("suppliers.id"), nullable=False, index=True)
    currency = db.Column(db.String(3), default="CDF", nullable=False)
    status = db.Column(db.String(20), default=PurchaseStatus.BROUILLON, nullable=False, index=True)

    order_date = db.Column(db.DateTime, default=utcnow, nullable=False)
    expected_date = db.Column(db.Date)
    received_at = db.Column(db.DateTime)

    montant_total = db.Column(db.Numeric(18, 2), default=Decimal("0"), nullable=False)
    # Reglement : paiement immediat a la reception ou credit (dette fournisseur).
    paid_now = db.Column(db.Boolean, default=True, nullable=False)

    created_by_id = db.Column(db.Integer, db.ForeignKey("users.id"))
    validated_by_id = db.Column(db.Integer, db.ForeignKey("users.id"))
    cancelled_by_id = db.Column(db.Integer, db.ForeignKey("users.id"))
    cancelled_at = db.Column(db.DateTime)
    cancel_reason = db.Column(db.String(255))
    notes = db.Column(db.Text)

    supplier = db.relationship("Supplier")
    created_by = db.relationship("User", foreign_keys=[created_by_id])
    validated_by = db.relationship("User", foreign_keys=[validated_by_id])
    cancelled_by = db.relationship("User", foreign_keys=[cancelled_by_id])
    lines = db.relationship(
        "PurchaseLine",
        back_populates="purchase",
        cascade="all, delete-orphan",
    )

    @property
    def is_editable(self):
        return self.status in (PurchaseStatus.BROUILLON, PurchaseStatus.COMMANDE)

    @property
    def quantity_total(self):
        return sum((Decimal(l.qty_base or 0) for l in self.lines), Decimal("0"))

    def __repr__(self):
        return f"<Purchase {self.reference} {self.status}>"


class PurchaseLine(BaseModel):
    __tablename__ = "purchase_lines"

    purchase_id = db.Column(db.Integer, db.ForeignKey("purchases.id"), nullable=False, index=True)
    product_id = db.Column(db.Integer, db.ForeignKey("products.id"), nullable=False)
    unit_id = db.Column(db.Integer, db.ForeignKey("units.id"))

    quantity = db.Column(db.Numeric(18, 3), default=Decimal("0"), nullable=False)
    qty_base = db.Column(db.Numeric(18, 3), default=Decimal("0"), nullable=False)
    prix_unitaire = db.Column(db.Numeric(18, 2), default=Decimal("0"), nullable=False)
    currency = db.Column(db.String(3), default="CDF", nullable=False)

    purchase = db.relationship("Purchase", back_populates="lines")
    product = db.relationship("Product")
    unit = db.relationship("Unit")

    @property
    def line_total(self):
        return (Decimal(self.quantity or 0) * Decimal(self.prix_unitaire or 0))

    def __repr__(self):
        return f"<PurchaseLine {self.product_id} {self.quantity}>"
