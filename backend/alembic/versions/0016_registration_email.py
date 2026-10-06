"""Add managed registration email settings and verification codes."""

import sqlalchemy as sa
from alembic import op

revision = '0016'
down_revision = '0015'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table('registration_settings',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('enabled', sa.Boolean(), nullable=False),
        sa.Column('smtp_host', sa.String(255), nullable=False),
        sa.Column('smtp_port', sa.Integer(), nullable=False),
        sa.Column('smtp_security', sa.String(20), nullable=False),
        sa.Column('smtp_username', sa.String(320), nullable=False),
        sa.Column('smtp_password_encrypted', sa.Text()),
        sa.Column('sender_email', sa.String(320), nullable=False),
        sa.Column('subject', sa.String(200), nullable=False),
        sa.Column('html_template', sa.Text(), nullable=False),
        sa.Column('template_vars', sa.JSON(), nullable=False),
        sa.Column('code_expiry_minutes', sa.Integer(), nullable=False))
    op.create_table('registration_codes',
        sa.Column('email', sa.String(320), primary_key=True),
        sa.Column('code_hash', sa.String(64), nullable=False),
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('sent_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('attempts', sa.Integer(), nullable=False))


def downgrade() -> None:
    op.drop_table('registration_codes')
    op.drop_table('registration_settings')
