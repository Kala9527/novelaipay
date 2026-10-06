"""Add announcements and revocable login sessions."""

import sqlalchemy as sa
from alembic import op

revision = '0013'
down_revision = '0012'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('users', sa.Column('session_version', sa.Integer(), nullable=False, server_default='0'))
    op.create_table('announcements',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('title', sa.String(120), nullable=False),
        sa.Column('body', sa.Text(), nullable=False),
        sa.Column('is_private', sa.Boolean(), nullable=False),
        sa.Column('starts_at', sa.DateTime(timezone=True)),
        sa.Column('ends_at', sa.DateTime(timezone=True)),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False))


def downgrade() -> None:
    op.drop_table('announcements')
    op.drop_column('users', 'session_version')
