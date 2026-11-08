"""Background LLM jobs: filling applications and the profile, profile match reports.

Jobs are stored in the database and run one at a time, in order of creation, by the worker (worker.py), so a slow
machine works through them while the user does something else, and a restart picks them up again. A job waits
while the model is starting and while an update is installed; an update can only be installed when no job is
waiting or running. Each kind of job is run by the handler its feature registers at startup (main.wire).
"""

import threading
from collections.abc import Callable
from datetime import UTC, datetime, timedelta

from sqlmodel import Session

from app.features.background_jobs import repository
from app.features.background_jobs.models import Job, TaskStatus
from app.shared.database import engine
from app.shared.llm import CancelToken

ACTIVE = repository.ACTIVE
# Finished jobs nobody dismissed are removed after this many days
KEEP_DAYS = 7


class JobHandler:
    """What a feature does for its kind of job. prepare runs with the database session open and returns the
    model call, which runs with no session open; finish and fail save the outcome unless the job was cancelled."""

    def prepare(self, session: Session, job: Job) -> Callable[[], object]:
        raise NotImplementedError

    def finish(self, session: Session, job: Job, result) -> None:
        pass

    def fail(self, session: Session, job: Job, error: str) -> None:
        pass

    def cancel(self, session: Session, job: Job) -> bool:
        """A waiting or running job is cancelled; True if the handler already removed the job."""
        return False

    def retry(self, session: Session, job: Job) -> None:
        pass

    def accept(self, session: Session, job: Job) -> None:
        """Apply job.proposal, the values found for fields the user had already filled."""

    def recover(self, session: Session) -> None:
        """At startup, after a restart."""

    def title(self, session: Session, job: Job) -> str | None:
        """Title of the application the job is about, shown in the jobs menu."""
        return None


_handlers: dict[str, JobHandler] = {}


def register(kind: str, handler: JobHandler) -> None:
    _handlers[kind] = handler


def handler(kind: str) -> JobHandler:
    return _handlers[kind]


# Set when there is something to do; the worker waits on it
wake_event = threading.Event()
_lock = threading.Lock()
# Job being run and the token that stops its model call
_running: tuple[int, CancelToken] | None = None


def now() -> datetime:
    return datetime.now(UTC)


def set_running(job_id: int | None, token: CancelToken | None = None) -> None:
    global _running
    with _lock:
        _running = (job_id, token) if job_id is not None else None


def stop_model(job_id: int | None = None) -> None:
    """Stop the model call of this job, or of whatever job is running."""
    with _lock:
        if _running and (job_id is None or _running[0] == job_id):
            _running[1].cancel()


def is_empty(value) -> bool:
    return value is None or value == "" or value == []


def split_result(current: dict, found: dict) -> tuple[dict, dict]:
    """Values for empty fields, applied right away, and for filled fields that differ, proposed."""
    fill, proposal = {}, {}
    for field, value in found.items():
        if is_empty(value):
            continue
        if is_empty(current.get(field)):
            fill[field] = value
        elif current[field] != value:
            proposal[field] = value
    return fill, proposal


# Queue

def enqueue(session: Session, job: Job) -> Job:
    """Add the job and commit, so the worker sees it."""
    repository.add(session, job)
    session.commit()
    session.refresh(job)
    wake_event.set()
    return job


def wake() -> None:
    """Jobs were added to the session and committed by the caller: start on them."""
    wake_event.set()


def find_active(session: Session, kind: str, user_id: int, application_id: int | None = None) -> Job | None:
    return repository.find_active(session, kind, user_id, application_id)


def count_active(session: Session) -> int:
    """Waiting and running jobs of all users."""
    return len(repository.active(session))


def positions(session: Session) -> dict[int, int]:
    """Place of every waiting job in the queue, shared by all users: 1 is the next one."""
    return {job_id: index for index, job_id in enumerate(repository.pending_ids(session), start=1)}


def stop_for_application(application_id: int) -> None:
    """The application is being deleted (its jobs go with it): stop the model if it is working on it."""
    with Session(engine) as session:
        ids = repository.ids_for_application(session, application_id)
    for job_id in ids:
        stop_model(job_id)


def cancel(session: Session, job: Job) -> None:
    """Remove a job. A running one stops the model; its handler undoes what the job started. Committed."""
    stop_model(job.id)
    if job.status in ACTIVE and handler(job.kind).cancel(session, job):
        return
    repository.delete(session, job)
    session.commit()


def cancel_all(session: Session) -> None:
    """AI turned off: waiting and running jobs are dropped. Applications they were creating stay, with
    their job posting, to be filled in by hand. Not committed."""
    for job in repository.active(session):
        stop_model(job.id)
        repository.delete(session, job)


def retry(session: Session, job: Job) -> Job:
    job.status, job.error, job.finished_at = TaskStatus.PENDING, None, None
    handler(job.kind).retry(session, job)
    return enqueue(session, job)


def accept(session: Session, job: Job) -> None:
    """The user accepts the values the model found for fields already filled. Committed."""
    if job.proposal:
        handler(job.kind).accept(session, job)
    repository.delete(session, job)
    session.commit()


def recover(session: Session) -> None:
    """At startup: jobs cut off by a restart run again, old finished jobs go away. Committed."""
    for job in repository.running(session):
        job.status = TaskStatus.PENDING
        repository.add(session, job)
    repository.delete_finished_before(session, now() - timedelta(days=KEEP_DAYS))
    for kind_handler in _handlers.values():
        kind_handler.recover(session)
    session.commit()


def titles(session: Session, jobs: list[Job]) -> dict[int, str | None]:
    return {job.id: handler(job.kind).title(session, job) for job in jobs}
