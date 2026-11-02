"""report queued after the AI fills a new application

Revision ID: 0019
Revises: 0018
Create Date: 2026-11-02
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0019"
down_revision: str | None = "0018"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("job", sa.Column("then_report", sa.Boolean(), server_default=sa.false(), nullable=False))


def downgrade() -> None:
    op.drop_column("job", "then_report")
