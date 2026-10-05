"""Allow hiding billing rows without changing wallet balances."""

import sqlalchemy as sa
from alembic import op

revision = '0009'
down_revision = '0008'
branch_labels = None
depends_on = None


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    for table in ('wallet_ledger', 'usage_records'):
        if 'hidden_at' not in {column['name'] for column in inspector.get_columns(table)}:
            op.add_column(table, sa.Column('hidden_at', sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    for table in ('wallet_ledger', 'usage_records'):
        op.drop_column(table, 'hidden_at')
