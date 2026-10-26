"""table notifications (messagerie et alertes)

Revision ID: c4d2a8e91f30
Revises: b7f1c2d94a10
Create Date: 2026-10-25 09:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'c4d2a8e91f30'
down_revision = 'b7f1c2d94a10'
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    if 'notifications' in sa.inspect(bind).get_table_names():
        return
    op.create_table(
        'notifications',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('uuid', sa.String(length=36), nullable=False),
        sa.Column('type', sa.String(length=30), nullable=False),
        sa.Column('title', sa.String(length=160), nullable=False),
        sa.Column('message', sa.Text(), nullable=False),
        sa.Column('link', sa.String(length=255), nullable=True),
        sa.Column('priority', sa.Integer(), nullable=False),
        sa.Column('read', sa.Boolean(), nullable=False),
        sa.Column('dismissed', sa.Boolean(), nullable=False),
        sa.Column('entity_type', sa.String(length=40), nullable=True),
        sa.Column('entity_id', sa.Integer(), nullable=True),
        sa.Column('entity_uuid', sa.String(length=36), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_notifications_uuid', 'notifications', ['uuid'], unique=True)
    op.create_index('ix_notifications_type', 'notifications', ['type'], unique=False)
    op.create_index('ix_notifications_read', 'notifications', ['read'], unique=False)
    op.create_index('ix_notifications_dismissed', 'notifications', ['dismissed'], unique=False)


def downgrade():
    op.drop_index('ix_notifications_dismissed', table_name='notifications')
    op.drop_index('ix_notifications_read', table_name='notifications')
    op.drop_index('ix_notifications_type', table_name='notifications')
    op.drop_index('ix_notifications_uuid', table_name='notifications')
    op.drop_table('notifications')
