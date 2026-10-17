"""expected salary as free text with period and gross/net, replacing RAL min/max

Revision ID: 0003
Revises: 0002
Create Date: 2026-10-17
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SYMBOLS = {"EUR": "€", "USD": "$", "GBP": "£"}


def _fmt(value: int) -> str:
    return f"{value:,}".replace(",", ".")


def upgrade() -> None:
    op.add_column("application", sa.Column("salary", sa.String(), nullable=True))
    op.add_column("application", sa.Column("salary_period", sa.String(10), nullable=True))
    op.add_column("application", sa.Column("salary_basis", sa.String(10), nullable=True))

    # The old RAL was always annual gross; without amounts keep the original text
    bind = op.get_bind()
    app = sa.table("application", sa.column("id"), sa.column("salary_min"), sa.column("salary_max"),
                   sa.column("salary_currency"), sa.column("salary_text"), sa.column("salary"),
                   sa.column("salary_period"), sa.column("salary_basis"))
    rows = bind.execute(sa.select(app.c.id, app.c.salary_min, app.c.salary_max, app.c.salary_currency,
                                  app.c.salary_text)).all()
    for row in rows:
        symbol = SYMBOLS.get(row.salary_currency or "EUR", row.salary_currency)
        if row.salary_min and row.salary_max and row.salary_min != row.salary_max:
            values = {"salary": f"{_fmt(row.salary_min)} – {_fmt(row.salary_max)} {symbol}"}
        elif row.salary_min or row.salary_max:
            prefix = "da " if not row.salary_max else "fino a " if not row.salary_min else ""
            values = {"salary": f"{prefix}{_fmt(row.salary_min or row.salary_max)} {symbol}"}
        elif row.salary_text:
            bind.execute(sa.update(app).where(app.c.id == row.id).values(salary=row.salary_text[:300]))
            continue
        else:
            continue
        bind.execute(sa.update(app).where(app.c.id == row.id)
                     .values(**values, salary_period="annual", salary_basis="gross"))

    for column in ("salary_min", "salary_max", "salary_currency", "salary_text"):
        op.drop_column("application", column)


def downgrade() -> None:
    op.add_column("application", sa.Column("salary_text", sa.String(), nullable=True))
    op.add_column("application", sa.Column("salary_currency", sa.String(8), nullable=True))
    op.add_column("application", sa.Column("salary_max", sa.Integer(), nullable=True))
    op.add_column("application", sa.Column("salary_min", sa.Integer(), nullable=True))
    op.execute("UPDATE application SET salary_text = salary")
    for column in ("salary", "salary_period", "salary_basis"):
        op.drop_column("application", column)
