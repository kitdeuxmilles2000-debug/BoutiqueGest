"""produits : famille, couleur, type de mesure, marge cible ; unites g, kg, cm, m

Revision ID: d5e7f1a2b3c4
Revises: c4d2a8e91f30
Create Date: 2026-10-25 12:00:00.000000

"""
import uuid
from datetime import datetime

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'd5e7f1a2b3c4'
down_revision = 'c4d2a8e91f30'
branch_labels = None
depends_on = None

NEW_UNITS = [
    ('G', 'Gramme', 'poids'),
    ('KG', 'Kilogramme', 'poids'),
    ('CM', 'Centimètre', 'longueur'),
    ('M', 'Mètre', 'longueur'),
]


def upgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    cols = {c['name'] for c in inspector.get_columns('products')}
    with op.batch_alter_table('products', schema=None) as batch_op:
        if 'famille' not in cols:
            batch_op.add_column(sa.Column('famille', sa.String(length=80), nullable=True))
            batch_op.create_index('ix_products_famille', ['famille'], unique=False)
        if 'couleur' not in cols:
            batch_op.add_column(sa.Column('couleur', sa.String(length=40), nullable=True))
            batch_op.create_index('ix_products_couleur', ['couleur'], unique=False)
        if 'type_mesure' not in cols:
            batch_op.add_column(sa.Column('type_mesure', sa.String(length=20),
                                          nullable=False, server_default='autre'))
        if 'marge_cible' not in cols:
            batch_op.add_column(sa.Column('marge_cible', sa.Numeric(precision=5, scale=2),
                                          nullable=True))

    units = sa.table('units',
                     sa.column('uuid', sa.String),
                     sa.column('code', sa.String),
                     sa.column('label', sa.String),
                     sa.column('kind', sa.String),
                     sa.column('is_system', sa.Boolean),
                     sa.column('created_at', sa.DateTime),
                     sa.column('updated_at', sa.DateTime))
    existing = {row[0] for row in bind.execute(sa.select(units.c.code)).fetchall()}
    now = datetime.utcnow()
    for code, label, kind in NEW_UNITS:
        if code not in existing:
            op.bulk_insert(units, [{
                'uuid': str(uuid.uuid4()), 'code': code, 'label': label, 'kind': kind,
                'is_system': True, 'created_at': now, 'updated_at': now,
            }])


def downgrade():
    bind = op.get_bind()
    cols = {c['name'] for c in sa.inspect(bind).get_columns('products')}
    with op.batch_alter_table('products', schema=None) as batch_op:
        if 'marge_cible' in cols:
            batch_op.drop_column('marge_cible')
        if 'type_mesure' in cols:
            batch_op.drop_column('type_mesure')
        if 'couleur' in cols:
            batch_op.drop_index('ix_products_couleur')
            batch_op.drop_column('couleur')
        if 'famille' in cols:
            batch_op.drop_index('ix_products_famille')
            batch_op.drop_column('famille')
