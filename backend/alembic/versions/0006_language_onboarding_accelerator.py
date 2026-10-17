"""settings: interface language, preferred accelerator, first-run wizard; status changes stored as codes

Revision ID: 0006
Revises: 0005
Create Date: 2026-10-17
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0006"
down_revision: str | None = "0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

LABELS = {
    "Da inviare": "applied",
    "Candidatura inviata": "applied",
    "Colloquio": "interview",
    "Offerta": "offer",
    "Rigettata": "rejected",
    "Completata": "completed",
}


def upgrade() -> None:
    op.add_column("app_settings", sa.Column("language", sa.String(5), server_default="it", nullable=False))
    op.add_column("app_settings", sa.Column("llm_accelerator", sa.String(10), server_default="auto", nullable=False))
    op.add_column("app_settings", sa.Column("onboarded", sa.Boolean(), server_default=sa.false(), nullable=False))

    # "Colloquio → Offerta" becomes "interview>offer", translated by the frontend
    bind = op.get_bind()
    event = sa.table("application_event", sa.column("id"), sa.column("type"), sa.column("title"))
    rows = bind.execute(sa.select(event.c.id, event.c.title).where(event.c.type == "status_change")).all()
    for row in rows:
        old, _, new = row.title.partition(" → ")
        if old in LABELS and new in LABELS:
            bind.execute(sa.update(event).where(event.c.id == row.id).values(title=f"{LABELS[old]}>{LABELS[new]}"))


def downgrade() -> None:
    names = {code: label for label, code in LABELS.items() if label != "Da inviare"}
    bind = op.get_bind()
    event = sa.table("application_event", sa.column("id"), sa.column("type"), sa.column("title"))
    rows = bind.execute(sa.select(event.c.id, event.c.title).where(event.c.type == "status_change")).all()
    for row in rows:
        old, _, new = row.title.partition(">")
        if old in names and new in names:
            bind.execute(sa.update(event).where(event.c.id == row.id).values(title=f"{names[old]} → {names[new]}"))
    for column in ("onboarded", "llm_accelerator", "language"):
        op.drop_column("app_settings", column)
