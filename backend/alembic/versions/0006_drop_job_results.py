"""Remove persisted image response metadata from generation jobs."""

import sqlalchemy as sa
from alembic import op

revision = '0006'
down_revision = '0005'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(sa.text('UPDATE generation_jobs SET result = NULL'))


def downgrade() -> None:
    pass
