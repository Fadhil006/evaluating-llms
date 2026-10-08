"""Persist response provenance for synthetic fixtures."""

import sqlalchemy as sa

from alembic import op

revision = "4c9f83a1b2d0"
down_revision = "ed883c60e12a"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("model_responses", sa.Column("provenance", sa.String(length=40),
                                                  server_default="live", nullable=False))


def downgrade() -> None:
    op.drop_column("model_responses", "provenance")
