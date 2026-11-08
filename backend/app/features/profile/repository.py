from sqlmodel import Session, select

from app.features.profile.models import Profile


def find_by_user(session: Session, user_id: int) -> Profile | None:
    return session.exec(select(Profile).where(Profile.user_id == user_id)).first()


def add(session: Session, profile: Profile) -> None:
    session.add(profile)
