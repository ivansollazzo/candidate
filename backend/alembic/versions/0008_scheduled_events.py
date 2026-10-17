"""events: start time and completion; "next step" dates become scheduled events

Revision ID: 0008
Revises: 0007
Create Date: 2026-10-17
"""
from collections.abc import Sequence
from datetime import date

import sqlalchemy as sa
from alembic import op

revision: str = "0008"
down_revision: str | None = "0007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

NEXT_STEP = {"it": "Prossimo step", "en": "Next step"}


def upgrade() -> None:
    op.add_column("application_event", sa.Column("starts_at", sa.Time(), nullable=True))
    op.add_column("application_event", sa.Column("completed", sa.Boolean(), server_default=sa.false(), nullable=False))

    bind = op.get_bind()
    event = sa.table("application_event", sa.column("application_id"), sa.column("type"), sa.column("occurred_on"),
                     sa.column("title"), sa.column("completed"))
    # Events already recorded in the past have happened
    bind.execute(sa.update(event).where(event.c.occurred_on <= date.today()).values(completed=True))

    # The old "next step" becomes a scheduled follow-up
    language = bind.execute(sa.text("SELECT language FROM app_settings WHERE id = 1")).scalar() or "it"
    title = NEXT_STEP.get(language, NEXT_STEP["it"])
    application = sa.table("application", sa.column("id"), sa.column("next_step_on"))
    rows = bind.execute(sa.select(application.c.id, application.c.next_step_on)
                        .where(application.c.next_step_on.is_not(None))).all()
    for row in rows:
        bind.execute(sa.insert(event).values(application_id=row.id, type="follow_up", occurred_on=row.next_step_on,
                                             title=title, completed=False))
    op.drop_column("application", "next_step_on")


def downgrade() -> None:
    op.add_column("application", sa.Column("next_step_on", sa.Date(), nullable=True))
    op.execute("""
        UPDATE application SET next_step_on = (
            SELECT min(occurred_on) FROM application_event
            WHERE application_event.application_id = application.id AND NOT completed AND type <> 'status_change'
        )
    """)
    op.drop_column("application_event", "completed")
    op.drop_column("application_event", "starts_at")
