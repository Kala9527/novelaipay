"""Store newly issued API keys encrypted for owner-initiated copying."""

import sqlalchemy as sa
from alembic import op

revision = '0004'
down_revision = '0003'
branch_labels = None
depends_on = None


def upgrade() -> None:
    columns = {column['name'] for column in sa.inspect(op.get_bind()).get_columns('api_keys')}
    if 'encrypted_key' not in columns:
        op.add_column('api_keys', sa.Column('encrypted_key', sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column('api_keys', 'encrypted_key')
