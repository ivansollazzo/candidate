from sqlmodel import Session

from app.features.settings.models import AppSettings

SETTINGS_ID = 1


def get(session: Session) -> AppSettings | None:
    return session.get(AppSettings, SETTINGS_ID)


def add(session: Session, settings: AppSettings) -> None:
    session.add(settings)
