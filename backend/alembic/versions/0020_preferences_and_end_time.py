"""report preference and overview layout on the user, end time of events

Revision ID: 0020
Revises: 0019
Create Date: 2026-11-02
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision: str = "0020"
down_revision: str | None = "0019"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("app_user", sa.Column("report_after_fill", sa.Boolean(), server_default=sa.false(), nullable=False))
    op.add_column("app_user", sa.Column("overview_layout", JSONB(), nullable=True))
    op.add_column("application_event", sa.Column("ends_at", sa.Time(), nullable=True))


def downgrade() -> None:
    op.drop_column("application_event", "ends_at")
    op.drop_column("app_user", "overview_layout")
    op.drop_column("app_user", "report_after_fill")
