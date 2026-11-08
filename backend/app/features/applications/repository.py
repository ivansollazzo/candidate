from sqlalchemy import case
from sqlmodel import Session, func, select

from app.features.applications.models import Application, ApplicationEvent, EventType


def get(session: Session, application_id: int) -> Application | None:
    return session.get(Application, application_id)


def add(session: Session, row) -> None:
    """Add an application, event or attachment."""
    session.add(row)


def delete(session: Session, row) -> None:
    """Delete an application (with its events and attachments), an event or an attachment."""
    session.delete(row)


def list_with_last_event(session: Session, user_id: int) -> list[tuple[Application, object]]:
    """The user's applications, most recently changed first, each with the date of its last event that is not a
    status change."""
    is_status = ApplicationEvent.type == EventType.STATUS_CHANGE
    last_event = (
        select(ApplicationEvent.application_id,
               func.max(case((is_status, None), else_=ApplicationEvent.occurred_on)).label("last_event_on"))
        .group_by(ApplicationEvent.application_id)
        .subquery()
    )
    query = (
        select(Application, last_event.c.last_event_on)
        .outerjoin(last_event, last_event.c.application_id == Application.id)
        .where(Application.user_id == user_id)
        .order_by(Application.updated_at.desc())
    )
    return list(session.exec(query).all())


def get_event(session: Session, event_id: int) -> ApplicationEvent | None:
    return session.get(ApplicationEvent, event_id)


def agenda(session: Session, user_id: int) -> list[tuple[ApplicationEvent, Application]]:
    """All the user's events except status changes, which belong to the application history."""
    return list(session.exec(
        select(ApplicationEvent, Application)
        .join(Application)
        .where(Application.user_id == user_id, ApplicationEvent.type != EventType.STATUS_CHANGE)
        .order_by(ApplicationEvent.occurred_on, ApplicationEvent.starts_at, ApplicationEvent.id)
    ).all())
