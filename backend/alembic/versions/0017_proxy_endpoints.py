"""Add managed outbound proxies for upstream accounts."""

import sqlalchemy as sa
from alembic import op

revision = '0017'
down_revision = '0016'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table('proxy_endpoints',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('name', sa.String(80), nullable=False, unique=True),
        sa.Column('encrypted_url', sa.Text(), nullable=False))
    with op.batch_alter_table('upstream_accounts', naming_convention={
            'fk': 'fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s'}) as batch:
        batch.add_column(sa.Column('proxy_id', sa.Integer(),
            sa.ForeignKey('proxy_endpoints.id', name='fk_upstream_accounts_proxy_id')))


def downgrade() -> None:
    with op.batch_alter_table('upstream_accounts', naming_convention={
            'fk': 'fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s'}) as batch:
        batch.drop_column('proxy_id')
    op.drop_table('proxy_endpoints')
