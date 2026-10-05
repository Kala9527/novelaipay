"""Hide deleted usage from views while preserving financial audit rows."""

import sqlalchemy as sa
from alembic import op

revision = '0007'
down_revision = '0006'
branch_labels = None
depends_on = None


def upgrade() -> None:
    columns = {column['name'] for column in sa.inspect(op.get_bind()).get_columns('generation_jobs')}
    if 'hidden_at' not in columns:
        op.add_column('generation_jobs', sa.Column('hidden_at', sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column('generation_jobs', 'hidden_at')
