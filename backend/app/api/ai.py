"""LLM field filling: results go back to the frontend, which shows them in the form for the user to save."""

from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, HTTPException, UploadFile, status
from sqlmodel import Session

from app.api.uploads import read_upload
from app.db import get_session
from app.i18n import t
from app.api.applications import get_owned
from app.models import User
from app.schemas import AITaskRead
from app.services import ai_tasks, security
from app.services.app_settings import require_llm
from app.services.documents import UnsupportedDocument, extract_text
from app.services.extraction import extract_cv_fields, extract_job_fields
from app.services.users import find_profile
from app.services.webpage import FetchError, fetch_job_posting

router = APIRouter(prefix="/api/ai", tags=["ai"])

MIN_CHARS = 20


def _start(background: BackgroundTasks, user: User, fn, text: str) -> ai_tasks.AITask:
    task = ai_tasks.create(user.id)
    background.add_task(ai_tasks.run, task, fn, text)
    return task


@router.post("/job-posting", response_model=AITaskRead, status_code=status.HTTP_202_ACCEPTED)
async def fill_job_posting(
    background: BackgroundTasks,
    text: str | None = Form(None),
    url: str | None = Form(None),
    application_id: int | None = Form(None),
    file: UploadFile | None = File(None),
    user: User = Depends(security.current_user),
    session: Session = Depends(get_session),
):
    """Read the job posting (text, link, file or the stored one) and extract its fields in the background."""
    require_llm(session)
    if file is not None:
        try:
            source = extract_text(file.filename or "", await read_upload(file))
        except UnsupportedDocument as exc:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc)) from exc
    elif url:
        try:
            source = fetch_job_posting(url.strip())
        except FetchError as exc:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc)) from exc
    elif application_id is not None:
        source = get_owned(session, application_id, user).description
        if not source:
            raise HTTPException(status.HTTP_409_CONFLICT, t("no_saved_posting"))
    else:
        source = (text or "").strip()
    if len(source) < MIN_CHARS:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, t("posting_too_short"))

    task = _start(background, user, extract_job_fields, source)
    return AITaskRead(id=task.id, status=task.status, source_text=source)


@router.post("/cv", response_model=AITaskRead, status_code=status.HTTP_202_ACCEPTED)
def fill_profile_from_cv(background: BackgroundTasks, user: User = Depends(security.current_user),
                         session: Session = Depends(get_session)):
    """Extract profile fields from the uploaded CV."""
    require_llm(session)
    profile = find_profile(session, user.id)
    if profile is None or not profile.cv_text:
        raise HTTPException(status.HTTP_409_CONFLICT, t("upload_first_cv"))
    task = _start(background, user, extract_cv_fields, profile.cv_text)
    return AITaskRead(id=task.id, status=task.status)


@router.get("/tasks/{task_id}", response_model=AITaskRead)
def get_task(task_id: str, user: User = Depends(security.current_user)):
    task = ai_tasks.get(task_id)
    if task is None or task.user_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, t("task_not_found"))
    return AITaskRead(id=task.id, status=task.status, result=task.result, error=task.error)
