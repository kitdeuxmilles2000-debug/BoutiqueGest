"""Ventes, paiements, remboursements, caisses et clotures.

Une vente est **mono-devise** : tous ses articles et paiements partagent la devise
du registre de caisse utilise. Les devises ne sont donc jamais melangees.
"""
from decimal import Decimal

from app.extensions import db
from app.models.base import BaseModel, utcnow


class SaleStatus:
    BROUILLON = "brouillon"
    VALIDEE = "validee"
    ANNULEE = "annulee"
    REMBOURSEE = "remboursee"


SALE_STATUS_LABELS = {
    SaleStatus.BROUILLON: "Brouillon",
    SaleStatus.VALIDEE: "Validee",
    SaleStatus.ANNULEE: "Annulee",
    SaleStatus.REMBOURSEE: "Remboursee",
}


class PaymentMethod:
    ESPECE = "espece"
    CREDIT = "credit"
    BANQUE = "banque"


PAYMENT_LABELS = {
    PaymentMethod.ESPECE: "Especes",
    PaymentMethod.BANQUE: "Banque / virement",
}

# Moyens de paiement proposes au point de vente : especes (cash) et credit (a credit).
PAYMENT_LABELS_POS = {
    PaymentMethod.ESPECE: "Especes",
    PaymentMethod.CREDIT: "A credit",
}


class CashMovementKind:
    VENTE = "vente"
    REMBOURSEMENT = "remboursement"
    APPORT = "apport"
    RETRAIT = "retrait"
    DEPENSE = "depense"
    RECOUVREMENT = "recouvrement"  # reglement d'une creance client (entree)
    REGLEMENT = "reglement"        # paiement d'une dette fournisseur (sortie)


# Types qui font entrer de l'argent dans la caisse
CASH_IN_KINDS = {CashMovementKind.VENTE, CashMovementKind.APPORT, CashMovementKind.RECOUVREMENT}
# Types qui font sortir de l'argent de la caisse
CASH_OUT_KINDS = {
    CashMovementKind.REMBOURSEMENT,
    CashMovementKind.RETRAIT,
    CashMovementKind.DEPENSE,
    CashMovementKind.REGLEMENT,
}

CASH_MOVEMENT_LABELS = {
    CashMovementKind.VENTE: "Vente",
    CashMovementKind.REMBOURSEMENT: "Remboursement",
    CashMovementKind.APPORT: "Apport",
    CashMovementKind.RETRAIT: "Retrait",
    CashMovementKind.DEPENSE: "Depense",
    CashMovementKind.RECOUVREMENT: "Recouvrement credit client",
    CashMovementKind.REGLEMENT: "Reglement fournisseur",
}


class CashSessionStatus:
    OUVERTE = "ouverte"
    SOUMISE = "soumise"
    VALIDEE = "validee"


CASH_SESSION_STATUS_LABELS = {
    CashSessionStatus.OUVERTE: "Ouverte",
    CashSessionStatus.SOUMISE: "Soumise",
    CashSessionStatus.VALIDEE: "Validee",
}


class CashRegister(BaseModel):
    __tablename__ = "cash_registers"

    name = db.Column(db.String(80), unique=True, nullable=False)
    currency = db.Column(db.String(3), default="CDF", nullable=False)
    active = db.Column(db.Boolean, default=True, nullable=False)
    notes = db.Column(db.String(255))

    sessions = db.relationship("CashSession", back_populates="register")

    def __repr__(self):
        return f"<CashRegister {self.name} {self.currency}>"


class CashSession(BaseModel):
    __tablename__ = "cash_sessions"

    register_id = db.Column(db.Integer, db.ForeignKey("cash_registers.id"), nullable=False)
    vendeur_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    currency = db.Column(db.String(3), default="CDF", nullable=False)

    opened_at = db.Column(db.DateTime, default=utcnow, nullable=False)
    solde_initial = db.Column(db.Numeric(18, 2), default=Decimal("0"), nullable=False)

    status = db.Column(db.String(20), default=CashSessionStatus.OUVERTE, nullable=False)

    closed_at = db.Column(db.DateTime)
    solde_theorique = db.Column(db.Numeric(18, 2), default=Decimal("0"), nullable=False)
    solde_compte = db.Column(db.Numeric(18, 2))
    ecart = db.Column(db.Numeric(18, 2), default=Decimal("0"), nullable=False)
    motif_ecart = db.Column(db.String(255))

    validated_by_id = db.Column(db.Integer, db.ForeignKey("users.id"))
    validated_at = db.Column(db.DateTime)

    register = db.relationship("CashRegister", back_populates="sessions")
    vendeur = db.relationship("User", foreign_keys=[vendeur_id])
    validated_by = db.relationship("User", foreign_keys=[validated_by_id])
    movements = db.relationship(
        "CashMovement",
        back_populates="session",
        cascade="all, delete-orphan",
        order_by="CashMovement.created_at",
    )
    sales = db.relationship("Sale", back_populates="cash_session")

    @property
    def is_open(self):
        return self.status == CashSessionStatus.OUVERTE

    def compute_theorique(self):
        """solde_theorique = solde_initial + entrees - sorties."""
        total = self.solde_initial or Decimal("0")
        for m in self.movements:
            total += m.amount or Decimal("0")
        return total

    def __repr__(self):
        return f"<CashSession #{self.id} {self.status}>"


class CashMovement(BaseModel):
    __tablename__ = "cash_movements"

    session_id = db.Column(db.Integer, db.ForeignKey("cash_sessions.id"), nullable=False, index=True)
    kind = db.Column(db.String(20), nullable=False, index=True)
    amount = db.Column(db.Numeric(18, 2), nullable=False)  # signe : + entree / - sortie
    currency = db.Column(db.String(3), default="CDF", nullable=False)

    source_type = db.Column(db.String(40))
    source_uuid = db.Column(db.String(36), index=True)
    reason = db.Column(db.String(255))
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"))

    session = db.relationship("CashSession", back_populates="movements")
    user = db.relationship("User")

    def __repr__(self):
        return f"<CashMovement {self.kind} {self.amount}>"


class Sale(BaseModel):
    __tablename__ = "sales"

    numero = db.Column(db.String(30), unique=True, nullable=False, index=True)
    vendeur_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    cash_session_id = db.Column(db.Integer, db.ForeignKey("cash_sessions.id"))

    currency = db.Column(db.String(3), default="CDF", nullable=False)
    status = db.Column(db.String(20), default=SaleStatus.VALIDEE, nullable=False, index=True)

    montant_total = db.Column(db.Numeric(18, 2), default=Decimal("0"), nullable=False)
    remise = db.Column(db.Numeric(18, 2), default=Decimal("0"), nullable=False)
    montant_paye = db.Column(db.Numeric(18, 2), default=Decimal("0"), nullable=False)

    sale_origine_id = db.Column(db.Integer, db.ForeignKey("sales.id"))
    notes = db.Column(db.String(255))

    validated_at = db.Column(db.DateTime, default=utcnow)
    validated_by_id = db.Column(db.Integer, db.ForeignKey("users.id"))

    vendeur = db.relationship("User", foreign_keys=[vendeur_id])
    validated_by = db.relationship("User", foreign_keys=[validated_by_id])
    cash_session = db.relationship("CashSession", back_populates="sales")
    sale_origine = db.relationship("Sale", remote_side="Sale.id")
    lines = db.relationship(
        "SaleLine",
        back_populates="sale",
        cascade="all, delete-orphan",
        order_by="SaleLine.id",
    )
    payments = db.relationship(
        "Payment",
        back_populates="sale",
        cascade="all, delete-orphan",
        order_by="Payment.created_at",
    )
    refunds = db.relationship(
        "Refund",
        back_populates="sale",
        cascade="all, delete-orphan",
        order_by="Refund.created_at",
    )

    @property
    def total_cost(self):
        return sum(
            ((line.cout_unitaire_cmp or Decimal("0")) * (line.qty_base or Decimal("0")) for line in self.lines),
            Decimal("0"),
        )

    @property
    def marge(self):
        return (self.montant_total or Decimal("0")) - self.total_cost

    @property
    def is_active(self):
        return self.status == SaleStatus.VALIDEE

    def __repr__(self):
        return f"<Sale {self.numero}>"


class SaleLine(BaseModel):
    __tablename__ = "sale_lines"

    sale_id = db.Column(db.Integer, db.ForeignKey("sales.id"), nullable=False, index=True)
    product_id = db.Column(db.Integer, db.ForeignKey("products.id"), nullable=False)
    unit_id = db.Column(db.Integer, db.ForeignKey("units.id"))

    quantity = db.Column(db.Numeric(18, 3), nullable=False)   # quantite vendue dans l'unite
    qty_base = db.Column(db.Numeric(18, 3), nullable=False)   # quantite convertie en unite de base
    prix_unitaire = db.Column(db.Numeric(18, 2), default=Decimal("0"), nullable=False)
    remise_ligne = db.Column(db.Numeric(18, 2), default=Decimal("0"), nullable=False)
    cout_unitaire_cmp = db.Column(db.Numeric(18, 2), default=Decimal("0"), nullable=False)
    currency = db.Column(db.String(3), default="CDF", nullable=False)

    sale = db.relationship("Sale", back_populates="lines")
    product = db.relationship("Product")
    unit = db.relationship("Unit")

    @property
    def line_total(self):
        return (self.quantity or Decimal("0")) * (self.prix_unitaire or Decimal("0")) - (
            self.remise_ligne or Decimal("0")
        )

    def __repr__(self):
        return f"<SaleLine p={self.product_id} x{self.quantity}>"


class Payment(BaseModel):
    __tablename__ = "payments"

    sale_id = db.Column(db.Integer, db.ForeignKey("sales.id"), nullable=False, index=True)
    amount = db.Column(db.Numeric(18, 2), nullable=False)
    currency = db.Column(db.String(3), default="CDF", nullable=False)
    method = db.Column(db.String(20), default=PaymentMethod.ESPECE, nullable=False)
    reference = db.Column(db.String(80))
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"))

    sale = db.relationship("Sale", back_populates="payments")
    user = db.relationship("User")

    def __repr__(self):
        return f"<Payment {self.method} {self.amount} {self.currency}>"


class Refund(BaseModel):
    __tablename__ = "refunds"

    sale_id = db.Column(db.Integer, db.ForeignKey("sales.id"), nullable=False, index=True)
    amount = db.Column(db.Numeric(18, 2), nullable=False)
    currency = db.Column(db.String(3), default="CDF", nullable=False)
    method = db.Column(db.String(20), default=PaymentMethod.ESPECE, nullable=False)
    motif = db.Column(db.String(255))
    restock = db.Column(db.Boolean, default=True, nullable=False)

    authorized_by_id = db.Column(db.Integer, db.ForeignKey("users.id"))
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"))

    sale = db.relationship("Sale", back_populates="refunds")
    authorized_by = db.relationship("User", foreign_keys=[authorized_by_id])
    user = db.relationship("User", foreign_keys=[user_id])

    def __repr__(self):
        return f"<Refund {self.amount} {self.currency}>"
