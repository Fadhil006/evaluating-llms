"""Persist immutable local analysis snapshots."""

import sqlalchemy as sa

from alembic import op

revision = "8ac4d9132b10"
down_revision = "5f42c0d1a8b7"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "analysis_snapshots",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.current_timestamp()),
        sa.Column("experiment_id", sa.Integer(), sa.ForeignKey("experiments.id"), nullable=False),
        sa.Column("manifest", sa.JSON(), nullable=False),
        sa.Column("snapshot", sa.JSON(), nullable=False),
        sa.Column("content_sha256", sa.String(64), nullable=False),
    )
    op.create_index("ix_analysis_snapshots_experiment_id", "analysis_snapshots", ["experiment_id"])
    op.create_index("ix_analysis_snapshots_content_sha256", "analysis_snapshots", ["content_sha256"])


def downgrade() -> None:
    op.drop_index("ix_analysis_snapshots_content_sha256", table_name="analysis_snapshots")
    op.drop_index("ix_analysis_snapshots_experiment_id", table_name="analysis_snapshots")
    op.drop_table("analysis_snapshots")
