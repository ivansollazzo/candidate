from fastapi import APIRouter, Depends, HTTPException, status
from sqlmodel import Session

from app.core.i18n import t
from app.features.auth.dependencies import current_user
from app.features.auth.models import User
from app.features.background_jobs import repository
from app.features.background_jobs import service as jobs
from app.features.background_jobs.models import Job, TaskStatus
from app.features.background_jobs.schemas import JobRead
from app.features.settings.service import require_llm
from app.shared.database import get_session

router = APIRouter(prefix="/api/jobs", tags=["jobs"])


def get_owned_job(session: Session, job_id: int, user: User) -> Job:
    job = repository.get(session, job_id)
    if job is None or job.user_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, t("job_not_found"))
    return job


@router.get("", response_model=list[JobRead])
def list_jobs(user: User = Depends(current_user), session: Session = Depends(get_session)):
    """The user's jobs, waiting, running and finished (until dismissed), in order of creation."""
    rows = repository.list_for_user(session, user.id)
    places, titles = jobs.positions(session), jobs.titles(session, rows)
    return [JobRead.model_validate(job).model_copy(update={"application_title": titles[job.id],
                                                           "position": places.get(job.id)})
            for job in rows]


@router.delete("/{job_id}", status_code=status.HTTP_204_NO_CONTENT)
def cancel_job(job_id: int, user: User = Depends(current_user), session: Session = Depends(get_session)):
    """Cancel a waiting or running job (an application it is creating is deleted), or dismiss a finished one."""
    jobs.cancel(session, get_owned_job(session, job_id, user))


@router.post("/{job_id}/retry", response_model=JobRead, status_code=status.HTTP_202_ACCEPTED)
def retry_job(job_id: int, user: User = Depends(current_user), session: Session = Depends(get_session)):
    """Queue a failed job again."""
    require_llm(session)
    job = get_owned_job(session, job_id, user)
    if job.status != TaskStatus.FAILED:
        raise HTTPException(status.HTTP_409_CONFLICT, t("job_not_failed"))
    return jobs.retry(session, job)


@router.post("/{job_id}/accept", status_code=status.HTTP_204_NO_CONTENT)
def accept_job(job_id: int, user: User = Depends(current_user), session: Session = Depends(get_session)):
    """Apply the values the job proposed for fields that were already filled; the job is then dismissed."""
    job = get_owned_job(session, job_id, user)
    if job.status != TaskStatus.DONE:
        raise HTTPException(status.HTTP_409_CONFLICT, t("job_not_finished"))
    jobs.accept(session, job)
