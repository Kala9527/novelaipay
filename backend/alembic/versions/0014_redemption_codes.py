"""Add single-use redemption codes."""

import sqlalchemy as sa
from alembic import op

revision = '0014'
down_revision = '0013'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table('redemption_codes',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('code_hash', sa.String(64), nullable=False, unique=True),
        sa.Column('prefix', sa.String(12), nullable=False),
        sa.Column('amount', sa.Numeric(14, 4), nullable=False),
        sa.Column('created_by', sa.Integer(), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('redeemed_by', sa.Integer(), sa.ForeignKey('users.id')),
        sa.Column('redeemed_at', sa.DateTime(timezone=True)),
        sa.Column('deleted_at', sa.DateTime(timezone=True)))


def downgrade() -> None:
    op.drop_table('redemption_codes')
