"""branch followed for updates and how often to check

Revision ID: 0011
Revises: 0010
Create Date: 2026-10-19
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0011"
down_revision: str | None = "0010"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("app_settings", sa.Column("update_branch", sa.String(200), nullable=True))
    op.add_column("app_settings", sa.Column("update_check_hours", sa.Integer(), server_default="6", nullable=False))


def downgrade() -> None:
    op.drop_column("app_settings", "update_check_hours")
    op.drop_column("app_settings", "update_branch")
