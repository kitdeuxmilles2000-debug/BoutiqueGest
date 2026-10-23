"""validation entrees stock + historique

Revision ID: 5aa25cf3e96d
Revises: ceab172ef89b
Create Date: 2026-10-21 05:43:05.802236

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '5aa25cf3e96d'
down_revision = 'ceab172ef89b'
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    tables = inspector.get_table_names()
    has_table = 'stock_entry_requests' in tables

    if not has_table:
        op.create_table(
            'stock_entry_requests',
            sa.Column('reference', sa.String(length=40), nullable=False),
            sa.Column('product_id', sa.Integer(), nullable=False),
            sa.Column('currency', sa.String(length=3), nullable=False),
            sa.Column('status', sa.String(length=20), nullable=False),
            sa.Column('quantity', sa.Numeric(precision=18, scale=3), nullable=False),
            sa.Column('unit_id', sa.Integer(), nullable=True),
            sa.Column('qty_base', sa.Numeric(precision=18, scale=3), nullable=False),
            sa.Column('cost_unit', sa.Numeric(precision=18, scale=2), nullable=False),
            sa.Column('reason', sa.String(length=255), nullable=True),
            sa.Column('notes', sa.Text(), nullable=True),
            sa.Column('lot_number', sa.String(length=60), nullable=True),
            sa.Column('expiry_date', sa.Date(), nullable=True),
            sa.Column('supplier_id', sa.Integer(), nullable=True),
            sa.Column('purchase_id', sa.Integer(), nullable=True),
            sa.Column('created_by_id', sa.Integer(), nullable=True),
            sa.Column('validated_by_id', sa.Integer(), nullable=True),
            sa.Column('rejected_by_id', sa.Integer(), nullable=True),
            sa.Column('validated_at', sa.DateTime(), nullable=True),
            sa.Column('rejected_at', sa.DateTime(), nullable=True),
            sa.Column('reject_reason', sa.String(length=255), nullable=True),
            sa.Column('id', sa.Integer(), nullable=False),
            sa.Column('uuid', sa.String(length=36), nullable=False),
            sa.Column('created_at', sa.DateTime(), nullable=False),
            sa.Column('updated_at', sa.DateTime(), nullable=False),
            sa.ForeignKeyConstraint(['created_by_id'], ['users.id']),
            sa.ForeignKeyConstraint(['product_id'], ['products.id']),
            sa.ForeignKeyConstraint(['purchase_id'], ['purchases.id']),
            sa.ForeignKeyConstraint(['rejected_by_id'], ['users.id']),
            sa.ForeignKeyConstraint(['supplier_id'], ['suppliers.id']),
            sa.ForeignKeyConstraint(['unit_id'], ['units.id']),
            sa.ForeignKeyConstraint(['validated_by_id'], ['users.id']),
            sa.PrimaryKeyConstraint('id'),
        )
        with op.batch_alter_table('stock_entry_requests', schema=None) as batch_op:
            batch_op.create_index(batch_op.f('ix_stock_entry_requests_product_id'), ['product_id'], unique=False)
            batch_op.create_index(batch_op.f('ix_stock_entry_requests_reference'), ['reference'], unique=True)
            batch_op.create_index(batch_op.f('ix_stock_entry_requests_status'), ['status'], unique=False)
            batch_op.create_index(batch_op.f('ix_stock_entry_requests_uuid'), ['uuid'], unique=True)

    mv_cols = {c['name'] for c in sa.inspect(bind).get_columns('stock_movements')}
    if 'stock_entry_request_id' not in mv_cols:
        with op.batch_alter_table('stock_movements', schema=None) as batch_op:
            batch_op.add_column(sa.Column('stock_entry_request_id', sa.Integer(), nullable=True))
            batch_op.create_foreign_key('fk_stock_movements_stock_entry_request_id', 'stock_entry_requests', ['stock_entry_request_id'], ['id'])


def downgrade():
    bind = op.get_bind()
    mv_cols = {c['name'] for c in sa.inspect(bind).get_columns('stock_movements')}
    if 'stock_entry_request_id' in mv_cols:
        with op.batch_alter_table('stock_movements', schema=None) as batch_op:
            batch_op.drop_constraint('fk_stock_movements_stock_entry_request_id', type_='foreignkey')
            batch_op.drop_column('stock_entry_request_id')

    tables = sa.inspect(bind).get_table_names()
    if 'stock_entry_requests' in tables:
        with op.batch_alter_table('stock_entry_requests', schema=None) as batch_op:
            batch_op.drop_index(batch_op.f('ix_stock_entry_requests_uuid'))
            batch_op.drop_index(batch_op.f('ix_stock_entry_requests_status'))
            batch_op.drop_index(batch_op.f('ix_stock_entry_requests_reference'))
            batch_op.drop_index(batch_op.f('ix_stock_entry_requests_product_id'))
        op.drop_table('stock_entry_requests')
