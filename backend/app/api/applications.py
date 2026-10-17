from datetime import date

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status
from sqlmodel import Session, select

from app.db import get_session, save
from app.i18n import t
from app.models import Application, ApplicationEvent, EventType, TaskStatus, User
from app.schemas import (
    ApplicationRead,
    ApplicationSummary,
    ApplicationUpdate,
    MatchResult,
)
from app.services import security
from app.services.app_settings import require_llm
from app.services.extraction import generate_advice
from app.services.matching import compute_match
from app.services.users import find_profile

router = APIRouter(prefix="/api/applications", tags=["applications"])


def get_owned(session: Session, application_id: int, user: User) -> Application:
    """Fetch the user's application; other users' applications look nonexistent."""
    app = session.get(Application, application_id)
    if app is None or app.user_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, t("application_not_found"))
    return app


@router.get("", response_model=list[ApplicationSummary])
def list_applications(user: User = Depends(security.current_user), session: Session = Depends(get_session)):
    # Search and status filtering happen in the frontend
    query = select(Application).where(Application.user_id == user.id).order_by(Application.updated_at.desc())
    return session.exec(query).all()


@router.post("", response_model=ApplicationRead, status_code=status.HTTP_201_CREATED)
def create_application(
    payload: ApplicationUpdate, user: User = Depends(security.current_user),
    session: Session = Depends(get_session),
):
    """Create an application with fields filled by hand or by the LLM (see /api/ai)."""
    app = Application(**payload.model_dump(exclude_unset=True), user_id=user.id)
    return save(session, app)


@router.get("/{application_id}", response_model=ApplicationRead)
def get_application(
    application_id: int, user: User = Depends(security.current_user),
    session: Session = Depends(get_session),
):
    return get_owned(session, application_id, user)


@router.patch("/{application_id}", response_model=ApplicationRead)
def update_application(
    application_id: int, payload: ApplicationUpdate, user: User = Depends(security.current_user),
    session: Session = Depends(get_session),
):
    app = get_owned(session, application_id, user)
    changes = payload.model_dump(exclude_unset=True)

    new_status = changes.get("status")
    if new_status and new_status != app.status:
        # Every status change is kept in the history
        session.add(ApplicationEvent(
            application_id=app.id,
            type=EventType.STATUS_CHANGE,
            occurred_on=date.today(),
            completed=True,
            # Statuses stored as codes ("applied>interview"); the frontend localizes them
            title=f"{app.status}>{new_status}",
        ))

    if changes.get("skills") is not None:
        # Advice depends on skills, so it must be regenerated
        app.advice_status = None
    for field, value in changes.items():
        setattr(app, field, value)
    return save(session, app)


@router.delete("/{application_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_application(
    application_id: int, user: User = Depends(security.current_user),
    session: Session = Depends(get_session),
):
    session.delete(get_owned(session, application_id, user))
    session.commit()


@router.get("/{application_id}/match", response_model=MatchResult)
def get_match(
    application_id: int, user: User = Depends(security.current_user),
    session: Session = Depends(get_session),
):
    app = get_owned(session, application_id, user)
    return compute_match(app, find_profile(session, user.id))


@router.post("/{application_id}/advice", response_model=ApplicationRead, status_code=status.HTTP_202_ACCEPTED)
def request_advice(
    application_id: int, background: BackgroundTasks, user: User = Depends(security.current_user),
    session: Session = Depends(get_session),
):
    require_llm(session)
    app = get_owned(session, application_id, user)
    if app.advice_status == TaskStatus.RUNNING:
        raise HTTPException(status.HTTP_409_CONFLICT, t("advice_running"))
    app.advice_status = TaskStatus.PENDING
    session.add(app)
    session.commit()
    session.refresh(app)
    background.add_task(generate_advice, app.id)
    return app
