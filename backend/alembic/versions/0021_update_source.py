"""updates follow a channel or a branch

Revision ID: 0021
Revises: 0020
Create Date: 2026-11-02
"""
from collections.abc import Sequence

from alembic import op

revision: str = "0021"
down_revision: str | None = "0020"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # A branch picked before stays selected; none picked now means the stable channel
    op.alter_column("app_settings", "update_branch", new_column_name="update_source")


def downgrade() -> None:
    op.alter_column("app_settings", "update_source", new_column_name="update_branch")
