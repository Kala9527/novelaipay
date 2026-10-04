"""User profile, lifecycle and global concurrency limit.

Revision ID: 0002
Revises: 0001
"""
import sqlalchemy as sa
from alembic import op


revision = '0002'
down_revision = '0001'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Revision 0001 used current metadata; inspect columns so fresh installs and existing databases both migrate.
    columns = {column['name'] for column in sa.inspect(op.get_bind()).get_columns('users')}
    if 'display_name' not in columns:
        op.add_column('users', sa.Column('display_name', sa.String(80), nullable=False, server_default=''))
    if 'max_concurrency' not in columns:
        op.add_column('users', sa.Column('max_concurrency', sa.Integer(), nullable=False, server_default='2'))
    if 'deleted_at' not in columns:
        op.add_column('users', sa.Column('deleted_at', sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column('users', 'deleted_at')
    op.drop_column('users', 'max_concurrency')
    op.drop_column('users', 'display_name')
