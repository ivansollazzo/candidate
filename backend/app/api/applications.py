from datetime import date

from fastapi import APIRouter, BackgroundTasks, Depends, File, HTTPException, UploadFile, status
from fastapi.responses import FileResponse
from sqlmodel import Session, func, select

from app.db import get_session, save
from app.i18n import t
from app.models import Application, ApplicationAttachment, ApplicationEvent, EventType, TaskStatus, User
from app.schemas import (
    ApplicationBulk,
    ApplicationListItem,
    ApplicationRead,
    ApplicationUpdate,
)
from app.services import security
from app.services.app_settings import require_llm
from app.services.attachments import attachment_path, attachments_dir, remove_attachments, save_attachments
from app.services.report import generate_report

router = APIRouter(prefix="/api/applications", tags=["applications"])


def get_owned(session: Session, application_id: int, user: User) -> Application:
    """Fetch the user's application; other users' applications look nonexistent."""
    app = session.get(Application, application_id)
    if app is None or app.user_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, t("application_not_found"))
    return app


def change_status(session: Session, app: Application, new_status: str) -> None:
    """Set the status, keeping every change in the history."""
    if new_status == app.status:
        return
    session.add(ApplicationEvent(
        application_id=app.id,
        type=EventType.STATUS_CHANGE,
        occurred_on=date.today(),
        completed=True,
        # Statuses stored as codes ("applied>interview"); the frontend localizes them
        title=f"{app.status}>{new_status}",
    ))
    app.status = new_status


@router.get("", response_model=list[ApplicationListItem])
def list_applications(user: User = Depends(security.current_user), session: Session = Depends(get_session)):
    # Search, status filtering and sorting happen in the frontend
    last_event = (
        select(ApplicationEvent.application_id, func.max(ApplicationEvent.occurred_on).label("last_event_on"))
        .where(ApplicationEvent.type != EventType.STATUS_CHANGE)
        .group_by(ApplicationEvent.application_id)
        .subquery()
    )
    query = (
        select(Application, last_event.c.last_event_on)
        .outerjoin(last_event, last_event.c.application_id == Application.id)
        .where(Application.user_id == user.id)
        .order_by(Application.updated_at.desc())
    )
    return [
        ApplicationListItem.model_validate(app).model_copy(update={
            "last_event_on": last_on,
            "match_score": app.report.get("score") if app.report_status == TaskStatus.DONE and app.report else None,
        })
        for app, last_on in session.exec(query).all()
    ]


@router.post("", response_model=ApplicationRead, status_code=status.HTTP_201_CREATED)
def create_application(
    payload: ApplicationUpdate, user: User = Depends(security.current_user),
    session: Session = Depends(get_session),
):
    """Create an application with fields filled by hand or by the LLM (see /api/ai)."""
    app = Application(**payload.model_dump(exclude_unset=True), user_id=user.id)
    return save(session, app)


@router.post("/bulk", status_code=status.HTTP_204_NO_CONTENT)
def bulk_update(
    payload: ApplicationBulk, user: User = Depends(security.current_user),
    session: Session = Depends(get_session),
):
    """Apply one action to several applications; all of them or none (unknown ids fail the whole request)."""
    apps = [get_owned(session, application_id, user) for application_id in dict.fromkeys(payload.ids)]
    for app in apps:
        if payload.action == "delete":
            session.delete(app)
        else:
            change_status(session, app, payload.status)
            session.add(app)
    folders = [attachments_dir(app) for app in apps] if payload.action == "delete" else []
    session.commit()
    remove_attachments(folders)


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

    if new_status := changes.pop("status", None):
        change_status(session, app, new_status)

    # The report depends on the position's skills and requirements
    if app.report_status == TaskStatus.DONE and any(
        field in changes and changes[field] != getattr(app, field)
        for field in ("skills", "requirements", "nice_to_have")
    ):
        app.report_stale = True
    for field, value in changes.items():
        setattr(app, field, value)
    return save(session, app)


@router.delete("/{application_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_application(
    application_id: int, user: User = Depends(security.current_user),
    session: Session = Depends(get_session),
):
    app = get_owned(session, application_id, user)
    folder = attachments_dir(app)
    session.delete(app)
    session.commit()
    # Attached files go too, so they don't take up space
    remove_attachments([folder])


def get_attachment(app: Application, attachment_id: int) -> ApplicationAttachment:
    attachment = next((a for a in app.attachments if a.id == attachment_id), None)
    if attachment is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, t("attachment_not_found"))
    return attachment


@router.post("/{application_id}/attachments", response_model=ApplicationRead, status_code=status.HTTP_201_CREATED)
async def add_attachments(
    application_id: int, files: list[UploadFile] = File(...), user: User = Depends(security.current_user),
    session: Session = Depends(get_session),
):
    app = get_owned(session, application_id, user)
    attachments = await save_attachments(app, files)
    session.add_all(attachments)
    try:
        session.commit()
    except Exception:
        for attachment in attachments:
            attachment_path(app, attachment).unlink(missing_ok=True)
        raise
    session.refresh(app)
    return app


@router.get("/{application_id}/attachments/{attachment_id}")
def download_attachment(
    application_id: int, attachment_id: int, user: User = Depends(security.current_user),
    session: Session = Depends(get_session),
):
    app = get_owned(session, application_id, user)
    attachment = get_attachment(app, attachment_id)
    path = attachment_path(app, attachment)
    if not path.exists():
        raise HTTPException(status.HTTP_404_NOT_FOUND, t("attachment_not_found"))
    # Always served as a download, so an uploaded HTML or SVG file can't run in the app's origin
    return FileResponse(path, filename=attachment.filename, media_type="application/octet-stream",
                        headers={"X-Content-Type-Options": "nosniff"})


@router.delete("/{application_id}/attachments/{attachment_id}", response_model=ApplicationRead)
def delete_attachment(
    application_id: int, attachment_id: int, user: User = Depends(security.current_user),
    session: Session = Depends(get_session),
):
    app = get_owned(session, application_id, user)
    attachment = get_attachment(app, attachment_id)
    path = attachment_path(app, attachment)
    session.delete(attachment)
    session.commit()
    path.unlink(missing_ok=True)
    session.refresh(app)
    return app


@router.post("/{application_id}/report", response_model=ApplicationRead, status_code=status.HTTP_202_ACCEPTED)
def request_report(
    application_id: int, background: BackgroundTasks, user: User = Depends(security.current_user),
    session: Session = Depends(get_session),
):
    """Generate (or regenerate) the compatibility report with the local model."""
    require_llm(session)
    app = get_owned(session, application_id, user)
    if app.report_status in (TaskStatus.PENDING, TaskStatus.RUNNING):
        raise HTTPException(status.HTTP_409_CONFLICT, t("report_running"))
    app.report_status = TaskStatus.PENDING
    session.add(app)
    session.commit()
    session.refresh(app)
    background.add_task(generate_report, app.id)
    return app
