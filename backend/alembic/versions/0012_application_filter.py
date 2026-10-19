"""per-user status filter of the applications list

Revision ID: 0012
Revises: 0011
Create Date: 2026-10-19
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0012"
down_revision: str | None = "0011"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("app_user", sa.Column("application_filter", sa.String(20), server_default="all", nullable=False))


def downgrade() -> None:
    op.drop_column("app_user", "application_filter")
