"""Allow sale formats specific to a product.

Revision ID: 9c4e7a1b2d60
Revises: 7b9e2c1a8d43
Create Date: 2026-10-31 09:25:00.000000
"""
from alembic import op
import sqlalchemy as sa


revision = "9c4e7a1b2d60"
down_revision = "7b9e2c1a8d43"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("units", schema=None) as batch_op:
        batch_op.add_column(sa.Column("product_id", sa.Integer(), nullable=True))
        batch_op.create_index("ix_units_product_id", ["product_id"], unique=False)
        batch_op.create_foreign_key(
            "fk_units_product_id_products",
            "products",
            ["product_id"],
            ["id"],
            ondelete="CASCADE",
        )


def downgrade():
    with op.batch_alter_table("units", schema=None) as batch_op:
        batch_op.drop_constraint("fk_units_product_id_products", type_="foreignkey")
        batch_op.drop_index("ix_units_product_id")
        batch_op.drop_column("product_id")
