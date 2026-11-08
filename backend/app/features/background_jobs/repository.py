from datetime import datetime

from sqlalchemy import delete as delete_rows
from sqlmodel import Session, col, select

from app.features.background_jobs.models import Job, TaskStatus

ACTIVE = (TaskStatus.PENDING, TaskStatus.RUNNING)


def get(session: Session, job_id: int) -> Job | None:
    return session.get(Job, job_id)


def add(session: Session, job: Job) -> None:
    session.add(job)


def delete(session: Session, job: Job) -> None:
    session.delete(job)


def find_active(session: Session, kind: str, user_id: int, application_id: int | None = None) -> Job | None:
    query = select(Job).where(Job.kind == kind, Job.user_id == user_id, col(Job.status).in_(ACTIVE))
    if application_id is not None:
        query = query.where(Job.application_id == application_id)
    return session.exec(query).first()


def active(session: Session) -> list[Job]:
    """Waiting and running jobs of all users."""
    return list(session.exec(select(Job).where(col(Job.status).in_(ACTIVE))).all())


def pending_ids(session: Session) -> list[int]:
    return list(session.exec(select(Job.id).where(Job.status == TaskStatus.PENDING).order_by(Job.id)).all())


def next_pending(session: Session) -> Job | None:
    return session.exec(select(Job).where(Job.status == TaskStatus.PENDING).order_by(Job.id).limit(1)).first()


def ids_for_application(session: Session, application_id: int) -> list[int]:
    return list(session.exec(select(Job.id).where(Job.application_id == application_id)).all())


def running(session: Session) -> list[Job]:
    return list(session.exec(select(Job).where(Job.status == TaskStatus.RUNNING)).all())


def delete_finished_before(session: Session, moment: datetime) -> None:
    session.exec(delete_rows(Job).where(col(Job.status).not_in(ACTIVE), Job.finished_at < moment))


def active_application_ids(session: Session, kind: str):
    """Subquery: applications with a waiting or running job of this kind."""
    return select(Job.application_id).where(Job.kind == kind, col(Job.status).in_(ACTIVE))


def list_for_user(session: Session, user_id: int) -> list[Job]:
    return list(session.exec(select(Job).where(Job.user_id == user_id).order_by(Job.id)).all())
