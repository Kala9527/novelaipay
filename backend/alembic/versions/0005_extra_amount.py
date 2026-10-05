"""Optional per-generation surcharge for NovelAI models."""

import sqlalchemy as sa
from alembic import op

revision = '0005'
down_revision = '0004'
branch_labels = None
depends_on = None


def upgrade() -> None:
    columns = {column['name'] for column in sa.inspect(op.get_bind()).get_columns('price_versions')}
    if 'extra_amount' not in columns:
        op.add_column('price_versions', sa.Column('extra_amount', sa.Numeric(14, 4),
                      nullable=False, server_default='0'))


def downgrade() -> None:
    op.drop_column('price_versions', 'extra_amount')
