"""outbox messages : corps HTML des e-mails

Revision ID: f1a2b3c4d5e6
Revises: d5e7f1a2b3c4
Create Date: 2026-10-26 10:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'f1a2b3c4d5e6'
down_revision = 'd5e7f1a2b3c4'
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if 'outbox_messages' not in inspector.get_table_names():
        return
    columns = {column['name'] for column in inspector.get_columns('outbox_messages')}
    if 'body_html' in columns:
        return
    with op.batch_alter_table('outbox_messages') as batch_op:
        batch_op.add_column(sa.Column('body_html', sa.Text(), nullable=True))


def downgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if 'outbox_messages' not in inspector.get_table_names():
        return
    columns = {column['name'] for column in inspector.get_columns('outbox_messages')}
    if 'body_html' not in columns:
        return
    with op.batch_alter_table('outbox_messages') as batch_op:
        batch_op.drop_column('body_html')
