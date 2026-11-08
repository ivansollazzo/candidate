from collections.abc import Iterator
from datetime import UTC, datetime
from typing import Any

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB
from sqlmodel import Field, Session, create_engine

from app.core.config import get_settings

# Connections for every request in flight (app.main.MAX_IN_FLIGHT) plus the background threads
engine = create_engine(get_settings().database_url, pool_pre_ping=True, pool_size=10, max_overflow=40)


def get_session() -> Iterator[Session]:
    with Session(engine) as session:
        yield session


def save[T](session: Session, obj: T) -> T:
    """Commit one record and reload it from the database."""
    session.add(obj)
    session.commit()
    session.refresh(obj)
    return obj


# Column definitions shared by the models

def utcnow() -> datetime:
    return datetime.now(UTC)


def json_list() -> Any:
    return Field(default_factory=list, sa_column=sa.Column(JSONB, nullable=False, server_default="[]"))


def json_object() -> Any:
    return Field(default=None, sa_column=sa.Column(JSONB, nullable=True))


def timestamp(onupdate: bool = False) -> Any:
    return Field(
        default_factory=utcnow,
        sa_column=sa.Column(
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
            onupdate=utcnow if onupdate else None,
        ),
    )


def int_field(default: int) -> Any:
    return Field(default=default, sa_column_kwargs={"server_default": str(default)})


def bool_field(default: bool) -> Any:
    return Field(default=default, sa_column_kwargs={"server_default": sa.true() if default else sa.false()})
