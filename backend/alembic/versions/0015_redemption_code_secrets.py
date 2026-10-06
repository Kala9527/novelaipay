"""Store recoverable secrets for newly generated redemption codes."""

import sqlalchemy as sa
from alembic import op

revision = '0015'
down_revision = '0014'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('redemption_codes', sa.Column('encrypted_code', sa.Text()))


def downgrade() -> None:
    op.drop_column('redemption_codes', 'encrypted_code')
