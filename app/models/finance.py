"""Finances : depenses, credits (clients / fournisseurs), echeances et reglements."""
from decimal import Decimal

from app.extensions import db
from app.models.base import BaseModel, utcnow


class ExpenseStatus:
    SAISIE = "saisie"
    ATTENTE = "en_attente"
    VALIDEE = "validee"
    REJETEE = "rejetee"


EXPENSE_STATUS_LABELS = {
    ExpenseStatus.SAISIE: "Saisie",
    ExpenseStatus.ATTENTE: "En attente",
    ExpenseStatus.VALIDEE: "Validee",
    ExpenseStatus.REJETEE: "Rejetee",
}


class CreditType:
    CLIENT = "client"
    FOURNISSEUR = "fournisseur"


CREDIT_TYPE_LABELS = {
    CreditType.CLIENT: "Client (creance)",
    CreditType.FOURNISSEUR: "Fournisseur (dette)",
}


class CreditStatus:
    ACTIF = "actif"
    PARTIEL = "partiel"
    SOLDE = "solde"
    EN_RETARD = "en_retard"


CREDIT_STATUS_LABELS = {
    CreditStatus.ACTIF: "Actif",
    CreditStatus.PARTIEL: "Partiellement regle",
    CreditStatus.SOLDE: "Solde",
    CreditStatus.EN_RETARD: "En retard",
}


class InstallmentStatus:
    A_VENIR = "a_venir"
    ECHUE = "echue"
    PAYEE = "payee"


INSTALLMENT_STATUS_LABELS = {
    InstallmentStatus.A_VENIR: "A venir",
    InstallmentStatus.ECHUE: "Echue",
    InstallmentStatus.PAYEE: "Payee",
}


class ExpenseCategory(BaseModel):
    __tablename__ = "expense_categories"

    name = db.Column(db.String(80), unique=True, nullable=False)
    active = db.Column(db.Boolean, default=True, nullable=False)

    def __repr__(self):
        return f"<ExpenseCategory {self.name}>"


class Expense(BaseModel):
    __tablename__ = "expenses"

    reference = db.Column(db.String(30), unique=True, nullable=False, index=True)
    expense_date = db.Column(db.DateTime, default=utcnow, nullable=False)

    amount = db.Column(db.Numeric(18, 2), default=Decimal("0"), nullable=False)
    currency = db.Column(db.String(3), default="CDF", nullable=False)
    category_id = db.Column(db.Integer, db.ForeignKey("expense_categories.id"))
    motif = db.Column(db.String(255), nullable=False)
    beneficiary = db.Column(db.String(120))
    method = db.Column(db.String(20), default="espece", nullable=False)

    status = db.Column(db.String(20), default=ExpenseStatus.SAISIE, nullable=False, index=True)
    cash_session_id = db.Column(db.Integer, db.ForeignKey("cash_sessions.id"))

    created_by_id = db.Column(db.Integer, db.ForeignKey("users.id"))
    validated_by_id = db.Column(db.Integer, db.ForeignKey("users.id"))
    validated_at = db.Column(db.DateTime)
    reject_reason = db.Column(db.String(255))
    notes = db.Column(db.Text)

    category = db.relationship("ExpenseCategory")
    cash_session = db.relationship("CashSession")
    created_by = db.relationship("User", foreign_keys=[created_by_id])
    validated_by = db.relationship("User", foreign_keys=[validated_by_id])

    def __repr__(self):
        return f"<Expense {self.reference} {self.amount} {self.currency}>"


class Credit(BaseModel):
    __tablename__ = "credits"

    type = db.Column(db.String(20), nullable=False, index=True)  # client / fournisseur
    customer_id = db.Column(db.Integer, db.ForeignKey("customers.id"))
    supplier_id = db.Column(db.Integer, db.ForeignKey("suppliers.id"))

    amount_initial = db.Column(db.Numeric(18, 2), default=Decimal("0"), nullable=False)
    amount_remaining = db.Column(db.Numeric(18, 2), default=Decimal("0"), nullable=False)
    currency = db.Column(db.String(3), default="CDF", nullable=False)

    status = db.Column(db.String(20), default=CreditStatus.ACTIF, nullable=False, index=True)
    due_date = db.Column(db.Date)
    sale_id = db.Column(db.Integer, db.ForeignKey("sales.id"))
    notes = db.Column(db.Text)
    created_by_id = db.Column(db.Integer, db.ForeignKey("users.id"))

    customer = db.relationship("Customer", back_populates="credits")
    supplier = db.relationship("Supplier")
    sale = db.relationship("Sale")
    created_by = db.relationship("User")
    installments = db.relationship(
        "Installment",
        back_populates="credit",
        cascade="all, delete-orphan",
        order_by="Installment.due_date",
    )
    settlements = db.relationship(
        "Settlement",
        back_populates="credit",
        cascade="all, delete-orphan",
        order_by="Settlement.created_at",
    )

    @property
    def partner_name(self):
        if self.customer is not None:
            return self.customer.name
        if self.supplier is not None:
            return self.supplier.name
        return "—"

    @property
    def is_client(self):
        return self.type == CreditType.CLIENT

    @property
    def settled_total(self):
        return sum((s.amount or Decimal("0") for s in self.settlements), Decimal("0"))

    def __repr__(self):
        return f"<Credit {self.type} {self.amount_remaining} {self.currency}>"


class Installment(BaseModel):
    __tablename__ = "installments"

    credit_id = db.Column(db.Integer, db.ForeignKey("credits.id"), nullable=False, index=True)
    due_date = db.Column(db.Date, nullable=False)
    amount_due = db.Column(db.Numeric(18, 2), default=Decimal("0"), nullable=False)
    status = db.Column(db.String(20), default=InstallmentStatus.A_VENIR, nullable=False)

    credit = db.relationship("Credit", back_populates="installments")

    def __repr__(self):
        return f"<Installment {self.due_date} {self.amount_due}>"


class Settlement(BaseModel):
    __tablename__ = "settlements"

    credit_id = db.Column(db.Integer, db.ForeignKey("credits.id"), nullable=False, index=True)
    amount = db.Column(db.Numeric(18, 2), nullable=False)
    currency = db.Column(db.String(3), default="CDF", nullable=False)
    method = db.Column(db.String(20), default="espece", nullable=False)
    reference = db.Column(db.String(80))
    cash_session_id = db.Column(db.Integer, db.ForeignKey("cash_sessions.id"))
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"))

    credit = db.relationship("Credit", back_populates="settlements")
    cash_session = db.relationship("CashSession")
    user = db.relationship("User")

    def __repr__(self):
        return f"<Settlement {self.amount} {self.currency}>"
