"""Add dataset split, family, variant and review provenance."""

import sqlalchemy as sa

from alembic import op

revision = "5f42c0d1a8b7"
down_revision = "4c9f83a1b2d0"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("dataset_items", sa.Column("split", sa.String(40), server_default="legacy_unknown", nullable=False))
    op.add_column("dataset_items", sa.Column("family_id", sa.String(255), nullable=True))
    op.add_column("dataset_items", sa.Column("variant_id", sa.String(255), nullable=True))
    op.add_column("dataset_items", sa.Column("provenance", sa.JSON(), server_default="{}", nullable=False))
    op.add_column("dataset_items", sa.Column("review_status", sa.String(40), server_default="unreviewed", nullable=False))


def downgrade() -> None:
    op.drop_column("dataset_items", "review_status")
    op.drop_column("dataset_items", "provenance")
    op.drop_column("dataset_items", "variant_id")
    op.drop_column("dataset_items", "family_id")
    op.drop_column("dataset_items", "split")
