"""Keep configuration history while allowing administrators to archive it."""

import sqlalchemy as sa
from alembic import op

revision = '0012'
down_revision = '0011'
branch_labels = None
depends_on = None


def upgrade() -> None:
    for table in ('upstream_accounts', 'upstream_groups', 'model_mappings'):
        op.add_column(table, sa.Column('deleted_at', sa.DateTime(timezone=True)))


def downgrade() -> None:
    for table in ('model_mappings', 'upstream_groups', 'upstream_accounts'):
        op.drop_column(table, 'deleted_at')
