from collections.abc import Iterator

from sqlmodel import Session, create_engine

from app.config import get_settings

engine = create_engine(get_settings().database_url, pool_pre_ping=True)


def get_session() -> Iterator[Session]:
    with Session(engine) as session:
        yield session


def save[T](session: Session, obj: T) -> T:
    """Commit one record and reload it from the database."""
    session.add(obj)
    session.commit()
    session.refresh(obj)
    return obj
