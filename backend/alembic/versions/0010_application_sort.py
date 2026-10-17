"""per-user sort order of the applications list

Revision ID: 0010
Revises: 0009
Create Date: 2026-10-17
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0010"
down_revision: str | None = "0009"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("app_user", sa.Column("application_sort", sa.String(10), server_default="applied", nullable=False))


def downgrade() -> None:
    op.drop_column("app_user", "application_sort")
