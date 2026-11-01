"""sessions last 7 days of inactivity instead of 12 hours

Revision ID: 0016
Revises: 0015
Create Date: 2026-11-01
"""
from collections.abc import Sequence

from alembic import op

revision: str = "0016"
down_revision: str | None = "0015"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.alter_column("app_settings", "session_hours", server_default="168")
    # Only the old default changes; a length chosen by the admin is kept
    op.execute("UPDATE app_settings SET session_hours = 168 WHERE session_hours = 12")


def downgrade() -> None:
    op.alter_column("app_settings", "session_hours", server_default="12")
