"""Keep fractional base-unit costs precise.

Revision ID: c8d3e2f1a904
Revises: 4f6a8c2d1e90
Create Date: 2026-10-31 13:15:00.000000
"""
from alembic import op
import sqlalchemy as sa


revision = "c8d3e2f1a904"
down_revision = "4f6a8c2d1e90"
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    product_columns = {
        column["name"] for column in sa.inspect(bind).get_columns("products")
    }
    if "marque" not in product_columns:
        op.add_column("products", sa.Column("marque", sa.String(length=80), nullable=True))
    if "modele" not in product_columns:
        op.add_column("products", sa.Column("modele", sa.String(length=80), nullable=True))

    # SQLite stores Numeric values without enforcing the declared scale. Updating
    # the SQLAlchemy model is sufficient and avoids rebuilding tables that have
    # cyclic product/unit foreign keys and expression-based indexes.
    if bind.dialect.name != "sqlite":
        for table, column in (
            ("products", "cost_avg"),
            ("stock_movements", "cost_unit"),
            ("sale_lines", "cout_unitaire_cmp"),
        ):
            op.alter_column(
                table,
                column,
                existing_type=sa.Numeric(18, 2),
                type_=sa.Numeric(18, 6),
                existing_nullable=(column == "cost_unit"),
            )


def downgrade():
    bind = op.get_bind()
    if bind.dialect.name == "sqlite":
        return

    for table, column in (
        ("products", "cost_avg"),
        ("stock_movements", "cost_unit"),
        ("sale_lines", "cout_unitaire_cmp"),
    ):
        op.alter_column(
            table,
            column,
            existing_type=sa.Numeric(18, 6),
            type_=sa.Numeric(18, 2),
            existing_nullable=(column == "cost_unit"),
        )

    op.drop_column("products", "modele")
    op.drop_column("products", "marque")
