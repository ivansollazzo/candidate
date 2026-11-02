"""background jobs: LLM operations queued and run one at a time

Revision ID: 0018
Revises: 0017
Create Date: 2026-11-01
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision: str = "0018"
down_revision: str | None = "0017"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "job",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("app_user.id", ondelete="CASCADE"), nullable=False),
        sa.Column("kind", sa.String(20), nullable=False),
        sa.Column("application_id", sa.Integer(), sa.ForeignKey("application.id", ondelete="CASCADE"), nullable=True),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("new_application", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column("source_text", sa.Text(), nullable=True),
        sa.Column("source_url", sa.String(), nullable=True),
        sa.Column("proposal", JSONB(), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_job_user_id", "job", ["user_id"])
    op.create_index("ix_job_application_id", "job", ["application_id"])
    op.create_index("ix_job_status", "job", ["status"])
    # Reports left waiting by the previous version (generated in memory) are not queued: back to the last result
    op.execute("UPDATE application SET report_status = CASE WHEN report ? 'score' THEN 'done' ELSE NULL END "
               "WHERE report_status IN ('pending', 'running')")


def downgrade() -> None:
    op.drop_table("job")
