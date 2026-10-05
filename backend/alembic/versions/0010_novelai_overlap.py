"""Track NovelAI jobs whose account balance deltas overlap."""

import sqlalchemy as sa
from alembic import op

revision = '0010'
down_revision = '0009'
branch_labels = None
depends_on = None


def upgrade() -> None:
    columns = {column['name'] for column in sa.inspect(op.get_bind()).get_columns('generation_jobs')}
    if 'billing_overlap' not in columns:
        op.add_column('generation_jobs', sa.Column('billing_overlap', sa.Boolean(), nullable=False,
                                                    server_default=sa.false()))


def downgrade() -> None:
    op.drop_column('generation_jobs', 'billing_overlap')
