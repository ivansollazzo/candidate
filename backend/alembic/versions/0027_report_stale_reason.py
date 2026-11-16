"""reports: the language each report was generated in, and why it should be regenerated (a reason, not a flag);
reports generated before 2.1 get the "update" reason

Revision ID: 0027
Revises: 0026
Create Date: 2026-11-16
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0027"
down_revision: str | None = "0026"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("application", sa.Column("report_language", sa.String(5), nullable=True))
    op.alter_column("application", "report_stale", server_default=None, nullable=True)
    op.alter_column("application", "report_stale", type_=sa.String(20),
                    postgresql_using="CASE WHEN report_stale THEN 'changed' END")
    # A future update that improves reports suggests regenerating them with this same statement
    op.execute("UPDATE application SET report_stale = 'update' WHERE report_status = 'done' AND report_stale IS NULL")


def downgrade() -> None:
    op.alter_column("application", "report_stale", type_=sa.Boolean(), postgresql_using="report_stale IS NOT NULL")
    op.alter_column("application", "report_stale", server_default=sa.false(), nullable=False)
    op.drop_column("application", "report_language")
