from collections.abc import Iterator

from sqlmodel import Session, create_engine

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
