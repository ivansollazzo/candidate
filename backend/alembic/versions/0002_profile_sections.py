"""profile sections: links, projects, structured certifications, numeric skill levels

Revision ID: 0002
Revises: 0001
Create Date: 2026-10-17
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

LEVELS = {"beginner": 1, "intermediate": 2, "advanced": 3, "expert": 4}


def upgrade() -> None:
    op.add_column("profile", sa.Column("links", postgresql.JSONB(), server_default="[]", nullable=False))
    op.add_column("profile", sa.Column("projects", postgresql.JSONB(), server_default="[]", nullable=False))

    # Certifications from strings to objects, skill levels from text to 1-4
    bind = op.get_bind()
    profile = sa.table("profile", sa.column("id"), sa.column("skills", postgresql.JSONB()),
                       sa.column("certifications", postgresql.JSONB()))
    for row in bind.execute(sa.select(profile.c.id, profile.c.skills, profile.c.certifications)):
        certifications = [{"name": c} if isinstance(c, str) else c for c in row.certifications or []]
        skills = [
            {**s, "level": s["level"] if isinstance(s.get("level"), int) else LEVELS.get(s.get("level"), 2)}
            for s in row.skills or []
        ]
        bind.execute(profile.update().where(profile.c.id == row.id)
                     .values(skills=skills, certifications=certifications))


def downgrade() -> None:
    op.drop_column("profile", "projects")
    op.drop_column("profile", "links")
