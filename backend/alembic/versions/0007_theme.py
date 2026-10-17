"""settings: interface theme (light, dark, system)

Revision ID: 0007
Revises: 0006
Create Date: 2026-10-17
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0007"
down_revision: str | None = "0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("app_settings", sa.Column("theme", sa.String(10), server_default="system", nullable=False))


def downgrade() -> None:
    op.drop_column("app_settings", "theme")
