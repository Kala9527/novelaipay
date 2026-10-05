"""Add group-scoped keys, model routes and capacity limits."""

import sqlalchemy as sa
from alembic import op

revision = '0008'
down_revision = '0007'
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    if sa.inspect(bind).has_table('upstream_groups'):
        return
    op.create_table('upstream_groups',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('name', sa.String(80), nullable=False, unique=True),
        sa.Column('max_concurrency', sa.Integer(), nullable=False, server_default='10'),
        sa.Column('enabled', sa.Boolean(), nullable=False, server_default=sa.true()))
    op.create_table('group_accounts',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('group_id', sa.Integer(), sa.ForeignKey('upstream_groups.id'), nullable=False),
        sa.Column('account_id', sa.Integer(), sa.ForeignKey('upstream_accounts.id'), nullable=False),
        sa.UniqueConstraint('group_id', 'account_id', name='uq_group_account'))
    op.create_table('model_routes',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('model_mapping_id', sa.Integer(), sa.ForeignKey('model_mappings.id'), nullable=False),
        sa.Column('account_id', sa.Integer(), sa.ForeignKey('upstream_accounts.id'), nullable=False),
        sa.Column('upstream_model', sa.String(150), nullable=False),
        sa.UniqueConstraint('model_mapping_id', 'account_id', name='uq_model_route'))
    with op.batch_alter_table('upstream_accounts') as batch:
        batch.add_column(sa.Column('max_concurrency', sa.Integer(), nullable=False, server_default='10'))
    with op.batch_alter_table('api_keys') as batch:
        batch.add_column(sa.Column('group_id', sa.Integer(), sa.ForeignKey('upstream_groups.id', name='fk_api_keys_group_id'), nullable=True))
    with op.batch_alter_table('generation_jobs') as batch:
        batch.add_column(sa.Column('group_id', sa.Integer(), sa.ForeignKey('upstream_groups.id', name='fk_generation_jobs_group_id'), nullable=True))
    if bind.dialect.name == 'sqlite':
        legacy = sa.Table('model_mappings', sa.MetaData(), autoload_with=bind)
        for constraint in list(legacy.constraints):
            if isinstance(constraint, sa.UniqueConstraint) and {column.name for column in constraint.columns} == {'public_name'}:
                legacy.constraints.remove(constraint)
        with op.batch_alter_table('model_mappings', recreate='always', copy_from=legacy) as batch:
            batch.add_column(sa.Column('group_id', sa.Integer(), sa.ForeignKey('upstream_groups.id', name='fk_model_mappings_group_id'), nullable=True))
    else:
        with op.batch_alter_table('model_mappings') as batch:
            batch.add_column(sa.Column('group_id', sa.Integer(), sa.ForeignKey('upstream_groups.id', name='fk_model_mappings_group_id'), nullable=True))
            batch.drop_constraint('model_mappings_public_name_key', type_='unique')
    bind.execute(sa.text("INSERT INTO upstream_groups (id, name, max_concurrency, enabled) VALUES (1, '默认分组', 10, true)"))
    bind.execute(sa.text('UPDATE model_mappings SET group_id = 1'))
    bind.execute(sa.text('UPDATE api_keys SET group_id = 1'))
    bind.execute(sa.text('UPDATE generation_jobs SET group_id = 1'))
    bind.execute(sa.text('INSERT INTO group_accounts (group_id, account_id) SELECT 1, id FROM upstream_accounts'))
    bind.execute(sa.text('INSERT INTO model_routes (model_mapping_id, account_id, upstream_model) SELECT id, upstream_account_id, upstream_model FROM model_mappings'))
    with op.batch_alter_table('model_mappings') as batch:
        batch.alter_column('group_id', nullable=False)
        batch.create_unique_constraint('uq_group_public_model', ['group_id', 'public_name'])


def downgrade() -> None:
    with op.batch_alter_table('model_mappings') as batch:
        batch.drop_constraint('uq_group_public_model', type_='unique')
        batch.create_unique_constraint('model_mappings_public_name_key', ['public_name'])
        batch.drop_column('group_id')
    with op.batch_alter_table('generation_jobs') as batch:
        batch.drop_column('group_id')
    with op.batch_alter_table('api_keys') as batch:
        batch.drop_column('group_id')
    with op.batch_alter_table('upstream_accounts') as batch:
        batch.drop_column('max_concurrency')
    op.drop_table('model_routes')
    op.drop_table('group_accounts')
    op.drop_table('upstream_groups')
