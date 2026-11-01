from fastapi import APIRouter, Depends, HTTPException, status
from sqlmodel import Session, select

from app.db import get_session
from app.i18n import t
from app.models import Application, Job, TaskStatus, User
from app.schemas import JobRead
from app.services import jobs, security
from app.services.app_settings import require_llm

router = APIRouter(prefix="/api/jobs", tags=["jobs"])


def get_owned_job(session: Session, job_id: int, user: User) -> Job:
    job = session.get(Job, job_id)
    if job is None or job.user_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, t("job_not_found"))
    return job


@router.get("", response_model=list[JobRead])
def list_jobs(user: User = Depends(security.current_user), session: Session = Depends(get_session)):
    """The user's jobs, waiting, running and finished (until dismissed), in order of creation."""
    rows = session.exec(
        select(Job, Application.title).outerjoin(Application, Application.id == Job.application_id)
        .where(Job.user_id == user.id).order_by(Job.id)
    ).all()
    places = jobs.positions(session)
    return [JobRead.model_validate(job).model_copy(update={"application_title": title, "position": places.get(job.id)})
            for job, title in rows]


@router.delete("/{job_id}", status_code=status.HTTP_204_NO_CONTENT)
def cancel_job(job_id: int, user: User = Depends(security.current_user), session: Session = Depends(get_session)):
    """Cancel a waiting or running job (an application it is creating is deleted), or dismiss a finished one."""
    jobs.cancel(session, get_owned_job(session, job_id, user))


@router.post("/{job_id}/apply", status_code=status.HTTP_204_NO_CONTENT)
def apply_job(job_id: int, user: User = Depends(security.current_user), session: Session = Depends(get_session)):
    """Apply the values proposed for fields that were already filled."""
    job = get_owned_job(session, job_id, user)
    if job.status != TaskStatus.DONE:
        raise HTTPException(status.HTTP_409_CONFLICT, t("job_not_finished"))
    jobs.apply_proposal(session, job)


@router.post("/{job_id}/retry", response_model=JobRead)
def retry_job(job_id: int, user: User = Depends(security.current_user), session: Session = Depends(get_session)):
    require_llm(session)
    job = get_owned_job(session, job_id, user)
    if job.status != TaskStatus.FAILED:
        raise HTTPException(status.HTTP_409_CONFLICT, t("job_not_failed"))
    return jobs.retry(session, job)
