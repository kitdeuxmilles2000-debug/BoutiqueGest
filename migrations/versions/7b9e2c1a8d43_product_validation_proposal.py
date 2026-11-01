"""product validation and proposal

Revision ID: 7b9e2c1a8d43
Revises: f1a2b3c4d5e6
Create Date: 2026-10-29 11:30:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '7b9e2c1a8d43'
down_revision = 'f1a2b3c4d5e6'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('products', schema=None) as batch_op:
        batch_op.add_column(sa.Column('validation_status', sa.String(length=20), nullable=False, server_default='valide'))
        batch_op.add_column(sa.Column('proposed_by_id', sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column('validated_by_id', sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column('validated_at', sa.DateTime(), nullable=True))
        batch_op.add_column(sa.Column('validation_note', sa.String(length=255), nullable=True))
        batch_op.create_index(batch_op.f('ix_products_validation_status'), ['validation_status'], unique=False)
        batch_op.create_foreign_key('fk_products_proposed_by_id_users', 'users', ['proposed_by_id'], ['id'])
        batch_op.create_foreign_key('fk_products_validated_by_id_users', 'users', ['validated_by_id'], ['id'])


def downgrade():
    with op.batch_alter_table('products', schema=None) as batch_op:
        batch_op.drop_constraint('fk_products_validated_by_id_users', type_='foreignkey')
        batch_op.drop_constraint('fk_products_proposed_by_id_users', type_='foreignkey')
        batch_op.drop_index(batch_op.f('ix_products_validation_status'))
        batch_op.drop_column('validation_note')
        batch_op.drop_column('validated_at')
        batch_op.drop_column('validated_by_id')
        batch_op.drop_column('proposed_by_id')
        batch_op.drop_column('validation_status')
