"""The report columns of applications: only this feature writes them."""

from sqlalchemy import null, update
from sqlmodel import Session, col, select

from app.features.applications.models import Application
from app.features.background_jobs import repository as job_repository
from app.features.background_jobs.models import JobKind, TaskStatus


def mark_stale(session: Session, user_id: int) -> None:
    session.exec(update(Application)
                 .where(Application.user_id == user_id, Application.report_status == TaskStatus.DONE)
                 .values(report_stale=True))


def clear_all(session: Session) -> None:
    session.exec(update(Application).values(report=null(), report_status=None, report_stale=False))


def waiting_without_job(session: Session) -> list[Application]:
    """Applications whose report is waiting or running but has no job (e.g. removed with an older version)."""
    queued = job_repository.active_application_ids(session, JobKind.REPORT)
    return list(session.exec(select(Application).where(col(Application.report_status).in_(job_repository.ACTIVE),
                                                      col(Application.id).not_in(queued))).all())
