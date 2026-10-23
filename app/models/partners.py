"""Partenaires : clients et fournisseurs."""
from decimal import Decimal

from app.extensions import db
from app.models.base import BaseModel


class Supplier(BaseModel):
    __tablename__ = "suppliers"

    name = db.Column(db.String(120), unique=True, nullable=False)
    contact = db.Column(db.String(120))
    default_currency = db.Column(db.String(3), default="CDF", nullable=False)
    terms = db.Column(db.String(255))
    active = db.Column(db.Boolean, default=True, nullable=False)
    notes = db.Column(db.Text)

    def __repr__(self):
        return f"<Supplier {self.name}>"


class Customer(BaseModel):
    __tablename__ = "customers"

    name = db.Column(db.String(120), unique=True, nullable=False)
    contact = db.Column(db.String(120))
    credit_limit = db.Column(db.Numeric(18, 2), default=Decimal("0"), nullable=False)
    active = db.Column(db.Boolean, default=True, nullable=False)
    notes = db.Column(db.Text)

    credits = db.relationship("Credit", back_populates="customer")

    @property
    def outstanding(self):
        """Encours de credit client en cours (somme des soldes restants)."""
        return sum(
            (c.amount_remaining or Decimal("0") for c in self.credits if c.status != "solde"),
            Decimal("0"),
        )

    def __repr__(self):
        return f"<Customer {self.name}>"
