"""updates follow a branch again: no release channels

Revision ID: 0022
Revises: 0021
Create Date: 2026-11-02
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0022"
down_revision: str | None = "0021"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.alter_column("app_settings", "update_source", new_column_name="update_branch")
    # A channel ("@stable", "@beta") falls back to the default branch
    op.execute(sa.text("UPDATE app_settings SET update_branch = NULL WHERE update_branch LIKE '@%'"))


def downgrade() -> None:
    op.alter_column("app_settings", "update_branch", new_column_name="update_source")
