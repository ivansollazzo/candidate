"""files attached to applications

Revision ID: 0015
Revises: 0014
Create Date: 2026-11-01
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0015"
down_revision: str | None = "0014"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "application_attachment",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("application_id", sa.Integer(), sa.ForeignKey("application.id", ondelete="CASCADE"), nullable=False),
        sa.Column("filename", sa.String(255), nullable=False),
        sa.Column("stored_name", sa.String(64), nullable=False),
        sa.Column("content_type", sa.String(255), nullable=True),
        sa.Column("size", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )
    op.create_index("ix_application_attachment_application_id", "application_attachment", ["application_id"])


def downgrade() -> None:
    op.drop_index("ix_application_attachment_application_id", "application_attachment")
    op.drop_table("application_attachment")
