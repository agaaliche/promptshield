"""Add trial_machines table for machine-level trial lockout (S3).

Revision ID: s3_trial_lockout
Revises:
Create Date: 2025-01-01
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

revision = "s3_trial_lockout"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "trial_machines",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("machine_fingerprint", sa.String(128), nullable=False, unique=True, index=True),
        sa.Column("first_trial_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("user_email", sa.String(320), nullable=True),
    )


def downgrade() -> None:
    op.drop_table("trial_machines")
