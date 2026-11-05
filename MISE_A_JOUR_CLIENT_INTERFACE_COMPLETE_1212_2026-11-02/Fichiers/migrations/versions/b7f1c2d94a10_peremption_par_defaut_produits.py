"""peremption par defaut sur les produits

Revision ID: b7f1c2d94a10
Revises: 5aa25cf3e96d
Create Date: 2026-10-22 08:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'b7f1c2d94a10'
down_revision = '5aa25cf3e96d'
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    cols = {c['name'] for c in sa.inspect(bind).get_columns('products')}
    if 'default_expiry_date' not in cols:
        with op.batch_alter_table('products', schema=None) as batch_op:
            batch_op.add_column(sa.Column('default_expiry_date', sa.Date(), nullable=True))
    if 'shelf_life_days' not in cols:
        with op.batch_alter_table('products', schema=None) as batch_op:
            batch_op.add_column(sa.Column('shelf_life_days', sa.Integer(), nullable=True))


def downgrade():
    bind = op.get_bind()
    cols = {c['name'] for c in sa.inspect(bind).get_columns('products')}
    with op.batch_alter_table('products', schema=None) as batch_op:
        if 'shelf_life_days' in cols:
            batch_op.drop_column('shelf_life_days')
        if 'default_expiry_date' in cols:
            batch_op.drop_column('default_expiry_date')
