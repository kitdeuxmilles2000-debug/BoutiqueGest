"""Catalogue : unites, categories, produits, conversions et historique des prix."""
from decimal import Decimal

from app.extensions import db
from app.models.base import BaseModel


class UnitKind:
    VOLUME = "volume"
    CAPACITY = "contenance"
    PIECE = "piece"


class ProductKind:
    """Nature du produit (informatif)."""

    BOISSON = "boisson"
    EAU = "eau"
    LAIT = "lait"
    ACCESSOIRE = "accessoire"
    AUTRE = "autre"


class Unit(BaseModel):
    __tablename__ = "units"

    code = db.Column(db.String(20), unique=True, nullable=False)
    label = db.Column(db.String(60), nullable=False)
    kind = db.Column(db.String(20), nullable=False, default=UnitKind.PIECE)
    is_system = db.Column(db.Boolean, default=False, nullable=False)

    def __repr__(self):
        return f"<Unit {self.code}>"


class Category(BaseModel):
    __tablename__ = "categories"

    name = db.Column(db.String(80), unique=True, nullable=False)
    description = db.Column(db.String(255))
    active = db.Column(db.Boolean, default=True, nullable=False)

    products = db.relationship("Product", back_populates="category")

    def __repr__(self):
        return f"<Category {self.name}>"


class Product(BaseModel):
    __tablename__ = "products"

    code = db.Column(db.String(40), unique=True, nullable=False, index=True)
    name = db.Column(db.String(120), nullable=False, index=True)
    category_id = db.Column(db.Integer, db.ForeignKey("categories.id"))
    base_unit_id = db.Column(db.Integer, db.ForeignKey("units.id"), nullable=False)
    kind = db.Column(db.String(20), default=ProductKind.AUTRE, nullable=False)

    currency = db.Column(db.String(3), default="CDF", nullable=False)
    cost_avg = db.Column(db.Numeric(18, 2), default=Decimal("0"), nullable=False)
    stock_qty = db.Column(db.Numeric(18, 3), default=Decimal("0"), nullable=False)
    seuil_alerte = db.Column(db.Numeric(18, 3), default=Decimal("0"), nullable=False)

    is_perishable = db.Column(db.Boolean, default=False, nullable=False)
    track_lot = db.Column(db.Boolean, default=False, nullable=False)
    default_expiry_date = db.Column(db.Date)
    shelf_life_days = db.Column(db.Integer)
    active = db.Column(db.Boolean, default=True, nullable=False)
    notes = db.Column(db.Text)

    category = db.relationship("Category", back_populates="products")
    base_unit = db.relationship("Unit", foreign_keys=[base_unit_id])
    selling_units = db.relationship(
        "ProductUnit",
        back_populates="product",
        cascade="all, delete-orphan",
        order_by="ProductUnit.factor",
    )

    @property
    def stock_value(self):
        return (self.stock_qty or Decimal("0")) * (self.cost_avg or Decimal("0"))

    @property
    def is_out_of_stock(self):
        return (self.stock_qty or Decimal("0")) <= 0

    @property
    def is_low_stock(self):
        return (
            not self.is_out_of_stock
            and self.seuil_alerte is not None
            and (self.stock_qty or Decimal("0")) <= (self.seuil_alerte or Decimal("0"))
        )

    def conversion_for(self, unit_id):
        """Facteur vers l'unite de base pour une unite de vente (1 si unite de base)."""
        if unit_id is None or unit_id == self.base_unit_id:
            return Decimal("1")
        for pu in self.selling_units:
            if pu.unit_id == unit_id:
                return pu.factor or Decimal("1")
        return Decimal("1")

    def __repr__(self):
        return f"<Product {self.code} {self.name}>"


class ProductUnit(BaseModel):
    """Unite de vente d'un produit et sa conversion vers l'unite de base."""

    __tablename__ = "product_units"

    product_id = db.Column(db.Integer, db.ForeignKey("products.id"), nullable=False)
    unit_id = db.Column(db.Integer, db.ForeignKey("units.id"), nullable=False)
    factor = db.Column(db.Numeric(18, 4), nullable=False, default=Decimal("1"))
    prix_vente = db.Column(db.Numeric(18, 2), default=Decimal("0"), nullable=False)
    currency = db.Column(db.String(3), default="CDF", nullable=False)
    is_sale_default = db.Column(db.Boolean, default=False, nullable=False)
    active = db.Column(db.Boolean, default=True, nullable=False)

    product = db.relationship("Product", back_populates="selling_units")
    unit = db.relationship("Unit")

    __table_args__ = (
        db.UniqueConstraint("product_id", "unit_id", name="uq_product_unit"),
    )

    def __repr__(self):
        return f"<ProductUnit p={self.product_id} u={self.unit_id} x{self.factor}>"


class PriceKind:
    ACHAT = "achat"
    VENTE = "vente"


class PriceHistory(BaseModel):
    __tablename__ = "price_history"

    product_id = db.Column(db.Integer, db.ForeignKey("products.id"), nullable=False, index=True)
    kind = db.Column(db.String(10), nullable=False)
    prix = db.Column(db.Numeric(18, 2), nullable=False)
    currency = db.Column(db.String(3), default="CDF", nullable=False)
    date_effet = db.Column(db.DateTime)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"))

    product = db.relationship("Product")

    def __repr__(self):
        return f"<PriceHistory {self.kind} {self.prix} {self.currency}>"
