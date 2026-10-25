"""drop the model choice of a withdrawn 1.3 build: the model is set again by the llm service

Revision ID: 0014
Revises: 0013
Create Date: 2026-10-25
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0014"
down_revision: str | None = "0013"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_column("app_settings", "llm_model")


def downgrade() -> None:
    op.add_column("app_settings", sa.Column("llm_model", sa.String(50), server_default="gemma4:e2b", nullable=False))
