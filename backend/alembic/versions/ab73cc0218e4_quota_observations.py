"""persist provider free-request observations

Revision ID: ab73cc0218e4
Revises: d43689520030
"""

import sqlalchemy as sa

from alembic import op

revision = "ab73cc0218e4"
down_revision = "d43689520030"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("provider_account_states", sa.Column("quota_limit", sa.Integer(), nullable=True))
    op.add_column("provider_account_states", sa.Column("quota_used", sa.Integer(), nullable=True))
    op.add_column("provider_account_states", sa.Column("quota_app_count", sa.Integer(), nullable=False, server_default="0"))


def downgrade():
    op.drop_column("provider_account_states", "quota_app_count")
    op.drop_column("provider_account_states", "quota_used")
    op.drop_column("provider_account_states", "quota_limit")
