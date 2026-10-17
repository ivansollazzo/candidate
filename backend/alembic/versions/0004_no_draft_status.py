"""remove the draft status: applications start as applied

Revision ID: 0004
Revises: 0003
Create Date: 2026-10-17
"""
from collections.abc import Sequence

from alembic import op

revision: str = "0004"
down_revision: str | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        "UPDATE application SET status = 'applied', applied_on = COALESCE(applied_on, created_at::date) "
        "WHERE status = 'draft'"
    )


def downgrade() -> None:
    # The "draft" status is gone: those applications become applied
    pass
