"""prevent duplicate assignments for the same candidate set

Revision ID: ed883c60e12a
Revises: ab73cc0218e4
"""

import sqlalchemy as sa

from alembic import op

revision = "ed883c60e12a"
down_revision = "ab73cc0218e4"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("review_assignments", sa.Column("assignment_key", sa.String(length=64), nullable=True))
    with op.batch_alter_table("review_assignments") as batch:
        batch.create_unique_constraint("uq_review_assignment_candidate",
                                        ["experiment_id", "evaluator_label", "mode", "assignment_key"])


def downgrade():
    with op.batch_alter_table("review_assignments") as batch:
        batch.drop_constraint("uq_review_assignment_candidate", type_="unique")
    op.drop_column("review_assignments", "assignment_key")
