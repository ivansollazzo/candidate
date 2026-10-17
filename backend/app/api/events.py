"""Application events: interviews, follow-ups and other appointments to schedule and mark as done."""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlmodel import Session, select

from app.api.applications import get_owned
from app.db import get_session, save
from app.i18n import t
from app.models import Application, ApplicationEvent, EventType, User
from app.schemas import AgendaEvent, EventCreate, EventRead, EventUpdate
from app.services import security

router = APIRouter(prefix="/api/events", tags=["events"])


def _get(session: Session, event_id: int, user: User) -> ApplicationEvent:
    event = session.get(ApplicationEvent, event_id)
    if event is None or event.application.user_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, t("event_not_found"))
    return event


@router.get("", response_model=list[AgendaEvent])
def list_events(user: User = Depends(security.current_user), session: Session = Depends(get_session)):
    """All events except status changes, which belong to the application history."""
    rows = session.exec(
        select(ApplicationEvent, Application)
        .join(Application)
        .where(Application.user_id == user.id, ApplicationEvent.type != EventType.STATUS_CHANGE)
        .order_by(ApplicationEvent.occurred_on, ApplicationEvent.starts_at, ApplicationEvent.id)
    ).all()
    return [
        AgendaEvent(**EventRead.model_validate(event).model_dump(),
                    application_title=app.title, application_company=app.company)
        for event, app in rows
    ]


@router.post("", response_model=EventRead, status_code=status.HTTP_201_CREATED)
def add_event(payload: EventCreate, user: User = Depends(security.current_user),
              session: Session = Depends(get_session)):
    get_owned(session, payload.application_id, user)
    event = ApplicationEvent(**payload.model_dump())
    return save(session, event)


@router.patch("/{event_id}", response_model=EventRead)
def update_event(event_id: int, payload: EventUpdate, user: User = Depends(security.current_user),
                 session: Session = Depends(get_session)):
    event = _get(session, event_id, user)
    changes = payload.model_dump(exclude_unset=True)
    if any(changes.get(field, "") is None for field in ("type", "occurred_on", "title", "completed")):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, t("event_field_required"))
    for field, value in changes.items():
        setattr(event, field, value)
    return save(session, event)


@router.delete("/{event_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_event(event_id: int, user: User = Depends(security.current_user), session: Session = Depends(get_session)):
    session.delete(_get(session, event_id, user))
    session.commit()
