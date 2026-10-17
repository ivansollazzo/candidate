"""app settings (LLM on/off); applications and profile filled manually or with the LLM on request

Revision ID: 0005
Revises: 0004
Create Date: 2026-10-17
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0005"
down_revision: str | None = "0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "app_settings",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("llm_enabled", sa.Boolean(), server_default=sa.true(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.alter_column("application", "description", existing_type=sa.Text(), nullable=True)
    for table in ("application", "profile"):
        op.drop_column(table, "extraction_status")
        op.drop_column(table, "extraction_error")


def downgrade() -> None:
    op.add_column("profile", sa.Column("extraction_error", sa.Text(), nullable=True))
    op.add_column("profile", sa.Column("extraction_status", sa.String(20), nullable=True))
    op.add_column("application", sa.Column("extraction_error", sa.Text(), nullable=True))
    op.add_column("application", sa.Column("extraction_status", sa.String(20), server_default="done", nullable=False))
    op.execute("UPDATE application SET description = '' WHERE description IS NULL")
    op.alter_column("application", "description", existing_type=sa.Text(), nullable=False)
    op.drop_table("app_settings")
