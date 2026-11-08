from sqlmodel import Session, func, select

from app.features.auth.models import User, UserRole


def get(session: Session, user_id: int) -> User | None:
    return session.get(User, user_id)


def find_by_username(session: Session, username: str) -> User | None:
    return session.exec(select(User).where(User.username == username)).first()


def find_by(session: Session, field: str, value: str, exclude_id: int | None = None) -> User | None:
    query = select(User).where(getattr(User, field) == value)
    if exclude_id is not None:
        query = query.where(User.id != exclude_id)
    return session.exec(query).first()


def count(session: Session) -> int:
    return session.exec(select(func.count()).select_from(User)).one()


def admin_count(session: Session) -> int:
    return session.exec(select(func.count()).select_from(User).where(User.role == UserRole.ADMIN)).one()


def list_all(session: Session) -> list[User]:
    return list(session.exec(select(User).order_by(User.username)).all())


def add(session: Session, user: User) -> None:
    session.add(user)


def delete(session: Session, user: User) -> None:
    session.delete(user)
