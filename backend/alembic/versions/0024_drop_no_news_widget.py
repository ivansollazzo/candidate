"""overview: the "no news" widget is gone, saved layouts lose it

Revision ID: 0024
Revises: 0023
Create Date: 2026-11-08
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0024"
down_revision: str | None = "0023"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(sa.text("""
        UPDATE app_user SET overview_layout = (
            SELECT coalesce(jsonb_agg(widget), '[]'::jsonb)
            FROM jsonb_array_elements(overview_layout) AS widget
            WHERE widget->>'id' <> 'no_news'
        )
        WHERE overview_layout IS NOT NULL AND overview_layout @> '[{"id": "no_news"}]'
    """))


def downgrade() -> None:
    pass
