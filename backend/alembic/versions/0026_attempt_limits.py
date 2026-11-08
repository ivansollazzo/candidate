"""security: account lock and per-IP limit on failed attempts, each with its own switch, both off by default

Revision ID: 0026
Revises: 0025
Create Date: 2026-11-08
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0026"
down_revision: str | None = "0025"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("app_settings", sa.Column("account_lockout_enabled", sa.Boolean(), nullable=False,
                                            server_default=sa.false()))
    op.add_column("app_settings", sa.Column("ip_limit_enabled", sa.Boolean(), nullable=False,
                                            server_default=sa.false()))
    op.add_column("app_settings", sa.Column("ip_max_attempts", sa.Integer(), nullable=False, server_default="20"))
    op.add_column("app_settings", sa.Column("ip_block_minutes", sa.Integer(), nullable=False, server_default="15"))
    # 0 no longer means "off": the switch does
    op.execute("UPDATE app_settings SET max_login_attempts = 5 WHERE max_login_attempts < 1")


def downgrade() -> None:
    for column in ("ip_block_minutes", "ip_max_attempts", "ip_limit_enabled", "account_lockout_enabled"):
        op.drop_column("app_settings", column)
