"""Add private groups and explicit user membership."""

import sqlalchemy as sa
from alembic import op

revision = '0011'
down_revision = '0010'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('upstream_groups', sa.Column('is_private', sa.Boolean(), nullable=False,
                                              server_default=sa.false()))
    op.create_table('group_members',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('group_id', sa.Integer(), sa.ForeignKey('upstream_groups.id'), nullable=False),
        sa.Column('user_id', sa.Integer(), sa.ForeignKey('users.id'), nullable=False),
        sa.UniqueConstraint('group_id', 'user_id', name='uq_group_member'))
    op.create_index('ix_group_members_group_id', 'group_members', ['group_id'])
    op.create_index('ix_group_members_user_id', 'group_members', ['user_id'])


def downgrade() -> None:
    op.drop_index('ix_group_members_user_id', table_name='group_members')
    op.drop_index('ix_group_members_group_id', table_name='group_members')
    op.drop_table('group_members')
    op.drop_column('upstream_groups', 'is_private')
