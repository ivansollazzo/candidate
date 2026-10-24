"""local model chosen in the settings

Revision ID: 0013
Revises: 0012
Create Date: 2026-10-24
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0013"
down_revision: str | None = "0012"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("app_settings", sa.Column("llm_model", sa.String(50), server_default="gemma4:e2b", nullable=False))


def downgrade() -> None:
    op.drop_column("app_settings", "llm_model")
