from typing import Annotated

from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    HTTPException,
    Query,
    Response,
    UploadFile,
    status,
)
from fastapi.responses import FileResponse
from sqlalchemy import case
from sqlmodel import Session, func, select

from app.core.i18n import t
from app.models import (
    Application,
    ApplicationAttachment,
    ApplicationEvent,
    EventType,
    Job,
    JobKind,
    TaskStatus,
    User,
)
from app.schemas import (
    ApplicationListItem,
    ApplicationRead,
    ApplicationReports,
    ApplicationsUpdate,
    ApplicationUpdate,
    JobRead,
    ReportsQueued,
)
from app.services import jobs, security
from app.services.app_settings import require_llm
from app.services.applications import apply_changes, change_status, delete_applications
from app.services.attachments import attachment_path, save_attachments
from app.services.sources import check_length, read_job_posting
from app.shared.database import get_session, save

router = APIRouter(prefix="/api/applications", tags=["applications"])


def get_owned(session: Session, application_id: int, user: User) -> Application:
    """Fetch the user's application; other users' applications look nonexistent."""
    app = session.get(Application, application_id)
    if app is None or app.user_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, t("application_not_found"))
    return app


@router.get("", response_model=list[ApplicationListItem])
def list_applications(user: User = Depends(security.current_user), session: Session = Depends(get_session)):
    # Search, status filtering and sorting happen in the frontend
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
        .where(Application.user_id == user.id)
        .order_by(Application.updated_at.desc())
    )
    items = []
    for app, last_on in session.exec(query).all():
        report = app.report if app.report_status == TaskStatus.DONE and app.report else None
        items.append(ApplicationListItem.model_validate(app).model_copy(update={
            "last_event_on": last_on,
            "match_score": report.get("score") if report else None,
            "report_stale": bool(report) and app.report_stale,
            "missing_skills": [s["skill"] for s in (report or {}).get("skills", [])
                               if s.get("status") == "missing" and s.get("kind") != "soft"],
        }))
    return items


@router.post("", response_model=ApplicationRead, status_code=status.HTTP_201_CREATED)
def create_application(
    payload: ApplicationUpdate, response: Response, user: User = Depends(security.current_user),
    session: Session = Depends(get_session),
):
    """Create an application with fields filled by hand."""
    app = save(session, Application(**payload.model_dump(exclude_unset=True), user_id=user.id))
    response.headers["Location"] = f"/api/applications/{app.id}"
    return app


@router.post("/imports", response_model=ApplicationRead, status_code=status.HTTP_201_CREATED)
async def create_with_ai(
    response: Response,
    text: str | None = Form(None),
    url: str | None = Form(None),
    file: UploadFile | None = File(None),
    report: bool = Form(False),
    user: User = Depends(security.current_user),
    session: Session = Depends(get_session),
):
    """Save a new application with its job posting (text, link or file) right away; the local model fills
    in its fields in the background, then (with report) generates its profile match report.
    Cancelling the job before it is done deletes the application."""
    require_llm(session)
    source = await read_job_posting(text, url, file)
    if source is None:
        check_length("")
    link = url.strip() if url and file is None else None
    app = save(session, Application(user_id=user.id, description=source, source_url=link))
    jobs.enqueue(session, Job(user_id=user.id, kind=JobKind.APPLICATION, application_id=app.id,
                              new_application=True, then_report=report, source_text=source))
    session.refresh(app)
    response.headers["Location"] = f"/api/applications/{app.id}"
    return app


@router.post("/{application_id}/fills", response_model=JobRead, status_code=status.HTTP_202_ACCEPTED)
async def fill_with_ai(
    application_id: int,
    text: str | None = Form(None),
    url: str | None = Form(None),
    file: UploadFile | None = File(None),
    user: User = Depends(security.current_user),
    session: Session = Depends(get_session),
):
    """Fill the application again from a new job posting, or from the saved one. Empty fields are filled
    when the job is done; values for filled fields are proposed (accepted with POST /api/jobs/{id}/accept)."""
    require_llm(session)
    app = get_owned(session, application_id, user)
    if jobs.find_active(session, JobKind.APPLICATION, user.id, app.id):
        raise HTTPException(status.HTTP_409_CONFLICT, t("job_running"))
    source = await read_job_posting(text, url, file)
    if source is None:
        if not app.description:
            raise HTTPException(status.HTTP_409_CONFLICT, t("no_saved_posting"))
        source = app.description
        check_length(source)
    link = url.strip() if url and file is None else None
    return jobs.enqueue(session, Job(user_id=user.id, kind=JobKind.APPLICATION, application_id=app.id,
                                     source_text=source, source_url=link))


@router.patch("", status_code=status.HTTP_204_NO_CONTENT)
def update_applications(
    payload: ApplicationsUpdate, user: User = Depends(security.current_user),
    session: Session = Depends(get_session),
):
    """Move several applications to one status; all of them or none (unknown ids fail the whole request)."""
    for app in [get_owned(session, application_id, user) for application_id in dict.fromkeys(payload.ids)]:
        change_status(session, app, payload.status)
        session.add(app)
    session.commit()


@router.delete("", status_code=status.HTTP_204_NO_CONTENT)
def delete_many(
    ids: Annotated[list[int], Query(min_length=1, max_length=1000)],
    user: User = Depends(security.current_user), session: Session = Depends(get_session),
):
    """Delete several applications (?ids=1&ids=2); all of them or none."""
    delete_applications(session, [get_owned(session, application_id, user) for application_id in dict.fromkeys(ids)])


@router.post("/reports", response_model=ReportsQueued, status_code=status.HTTP_202_ACCEPTED)
def request_reports(
    payload: ApplicationReports, user: User = Depends(security.current_user),
    session: Session = Depends(get_session),
):
    """Queue the profile match report of several applications, one job each, in the order given. Applications
    without skills (nothing to compare) and those whose report is already queued are skipped."""
    require_llm(session)
    apps = [get_owned(session, application_id, user) for application_id in dict.fromkeys(payload.ids)]
    result = ReportsQueued(queued=0, without_skills=0, already_queued=0)
    for app in apps:
        if not app.skills:
            result.without_skills += 1
        elif jobs.find_active(session, JobKind.REPORT, user.id, app.id):
            result.already_queued += 1
        else:
            app.report_status = TaskStatus.PENDING
            session.add(app)
            session.add(Job(user_id=user.id, kind=JobKind.REPORT, application_id=app.id))
            result.queued += 1
    session.commit()
    jobs.wake()
    return result


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
    apply_changes(session, app, payload.model_dump(exclude_unset=True))
    return save(session, app)


@router.delete("/{application_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_application(
    application_id: int, user: User = Depends(security.current_user),
    session: Session = Depends(get_session),
):
    delete_applications(session, [get_owned(session, application_id, user)])


def get_attachment(app: Application, attachment_id: int) -> ApplicationAttachment:
    attachment = next((a for a in app.attachments if a.id == attachment_id), None)
    if attachment is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, t("attachment_not_found"))
    return attachment


@router.post("/{application_id}/attachments", response_model=ApplicationRead, status_code=status.HTTP_201_CREATED)
async def add_attachments(
    application_id: int, response: Response, files: list[UploadFile] = File(...),
    user: User = Depends(security.current_user),
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
    # The body is the whole application; Location names the new file when only one was added
    if len(attachments) == 1:
        response.headers["Location"] = f"/api/applications/{app.id}/attachments/{attachments[0].id}"
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
    application_id: int, user: User = Depends(security.current_user), session: Session = Depends(get_session),
):
    """Queue the generation (or regeneration) of the profile match report by the local model."""
    require_llm(session)
    app = get_owned(session, application_id, user)
    if jobs.find_active(session, JobKind.REPORT, user.id, app.id):
        raise HTTPException(status.HTTP_409_CONFLICT, t("report_running"))
    app.report_status = TaskStatus.PENDING
    session.add(app)
    jobs.enqueue(session, Job(user_id=user.id, kind=JobKind.REPORT, application_id=app.id))
    session.refresh(app)
    return app
