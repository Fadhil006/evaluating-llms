"""Align analysis snapshot timestamp nullability with the ORM."""

from alembic import op

revision = "f13a4c2b9d07"
down_revision = "8ac4d9132b10"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("analysis_snapshots") as batch:
        batch.alter_column("created_at", nullable=False)


def downgrade() -> None:
    with op.batch_alter_table("analysis_snapshots") as batch:
        batch.alter_column("created_at", nullable=True)
