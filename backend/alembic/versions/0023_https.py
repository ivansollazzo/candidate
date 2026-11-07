"""HTTPS settings: mode, hosts, uploaded certificates, internal authority

Revision ID: 0023
Revises: 0022
Create Date: 2026-11-08
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision: str = "0023"
down_revision: str | None = "0022"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("app_settings", sa.Column("https_mode", sa.String(10), nullable=False, server_default="off"))
    op.add_column("app_settings", sa.Column("https_hosts", JSONB, nullable=False, server_default="[]"))
    op.add_column("app_settings", sa.Column("https_certs", JSONB, nullable=False, server_default="[]"))
    op.add_column("app_settings", sa.Column("https_ca", JSONB, nullable=True))
    op.add_column("app_settings", sa.Column("https_leaf", JSONB, nullable=True))


def downgrade() -> None:
    for column in ("https_leaf", "https_ca", "https_certs", "https_hosts", "https_mode"):
        op.drop_column("app_settings", column)
