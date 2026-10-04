"""NovelAI provider, request parameters, and Anlas billing."""

import sqlalchemy as sa
from alembic import op

revision = '0003'
down_revision = '0002'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Revision 0001 builds current metadata on a fresh database.
    for table, columns in {
        'upstream_accounts': [
            sa.Column('provider', sa.String(20), nullable=False, server_default='openai'),
            sa.Column('opus_free', sa.Boolean(), nullable=False, server_default=sa.false()),
        ],
        'price_versions': [
            sa.Column('billing_mode', sa.String(20), nullable=False, server_default='fixed'),
        ],
        'generation_jobs': [
            sa.Column('parameters', sa.JSON(), nullable=False, server_default='{}'),
            sa.Column('anlas_cost', sa.Integer(), nullable=True),
        ],
    }.items():
        existing = {column['name'] for column in sa.inspect(op.get_bind()).get_columns(table)}
        with op.batch_alter_table(table) as batch:
            for column in columns:
                if column.name not in existing:
                    batch.add_column(column)


def downgrade() -> None:
    with op.batch_alter_table('generation_jobs') as batch:
        batch.drop_column('anlas_cost')
        batch.drop_column('parameters')
    with op.batch_alter_table('price_versions') as batch:
        batch.drop_column('billing_mode')
    with op.batch_alter_table('upstream_accounts') as batch:
        batch.drop_column('opus_free')
        batch.drop_column('provider')
