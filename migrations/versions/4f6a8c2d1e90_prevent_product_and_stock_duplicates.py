"""Prevent duplicate products and fingerprint stock entries.

Revision ID: 4f6a8c2d1e90
Revises: 9c4e7a1b2d60
Create Date: 2026-11-01 10:00:00.000000
"""
import unicodedata

from alembic import op
import sqlalchemy as sa


revision = "4f6a8c2d1e90"
down_revision = "9c4e7a1b2d60"
branch_labels = None
depends_on = None


def _normalize_name(value):
    normalized = unicodedata.normalize("NFKC", value or "")
    return " ".join(normalized.split()).casefold()


def upgrade():
    op.add_column(
        "products",
        sa.Column("normalized_name", sa.String(length=512), nullable=True),
    )
    connection = op.get_bind()
    rows = connection.execute(
        sa.text("SELECT id, name, category_id FROM products ORDER BY id")
    ).mappings()
    reserved = set()
    for row in rows:
        key = _normalize_name(row["name"])
        scope = row["category_id"] or 0
        if (scope, key) in reserved:
            key = f"{key}~legacy-{row['id']}"
        reserved.add((scope, key))
        connection.execute(
            sa.text("UPDATE products SET normalized_name = :key WHERE id = :id"),
            {"key": key, "id": row["id"]},
        )

    with op.batch_alter_table("products") as batch_op:
        batch_op.alter_column(
            "normalized_name",
            existing_type=sa.String(length=512),
            nullable=False,
        )
    op.create_index(
        "uq_products_category_name",
        "products",
        [sa.text("COALESCE(category_id, 0)"), "normalized_name"],
        unique=True,
    )

    with op.batch_alter_table("stock_entry_requests") as batch_op:
        batch_op.add_column(sa.Column("duplicate_signature", sa.String(length=64), nullable=True))
        batch_op.add_column(sa.Column("duplicate_approved_by_id", sa.Integer(), nullable=True))
        batch_op.create_foreign_key(
            "fk_stock_entry_requests_duplicate_approved_by_id_users",
            "users",
            ["duplicate_approved_by_id"],
            ["id"],
        )
    op.create_index(
        "ix_stock_entry_requests_duplicate_signature",
        "stock_entry_requests",
        ["duplicate_signature"],
        unique=True,
    )


def downgrade():
    op.drop_index(
        "ix_stock_entry_requests_duplicate_signature",
        table_name="stock_entry_requests",
    )
    with op.batch_alter_table("stock_entry_requests") as batch_op:
        batch_op.drop_constraint(
            "fk_stock_entry_requests_duplicate_approved_by_id_users",
            type_="foreignkey",
        )
        batch_op.drop_column("duplicate_approved_by_id")
        batch_op.drop_column("duplicate_signature")
    op.drop_index("uq_products_category_name", table_name="products")
    with op.batch_alter_table("products") as batch_op:
        batch_op.drop_column("normalized_name")
