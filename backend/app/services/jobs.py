"""Background LLM jobs: filling applications and the profile, compatibility reports.

Jobs are stored in the database and run one at a time, in order of creation, by a worker thread, so a slow
machine works through them while the user does something else, and a restart picks them up again. A job
waits while the model is starting and while an update is installed; an update can only be installed when no
job is waiting or running.
"""

import logging
import threading
from collections.abc import Callable
from datetime import UTC, datetime, timedelta

from sqlalchemy import delete
from sqlmodel import Session, col, select

from app.core.i18n import current_language, t
from app.models import Application, Job, JobKind, TaskStatus, User
from app.services import app_settings, report
from app.services.applications import apply_changes, delete_applications
from app.services.extraction import extract_cv_fields, extract_job_fields
from app.services.profiles import apply_profile_changes
from app.services.users import find_profile
from app.shared import maintenance
from app.shared.database import engine
from app.shared.llm import Cancelled, CancelToken, LLMError, cancel_token, check_llm

log = logging.getLogger(__name__)

ACTIVE = (TaskStatus.PENDING, TaskStatus.RUNNING)
# Seconds between checks while waiting for jobs, the model or an update
POLL_SECONDS = 5
# Finished jobs nobody dismissed are removed after this many days
KEEP_DAYS = 7

_wake = threading.Event()
_stop = threading.Event()
_lock = threading.Lock()
# Job being run and the token that stops its model call
_running: tuple[int, CancelToken] | None = None
_thread: threading.Thread | None = None


def now() -> datetime:
    return datetime.now(UTC)


def is_empty(value) -> bool:
    return value is None or value == "" or value == []


# Queue

def enqueue(session: Session, job: Job) -> Job:
    session.add(job)
    session.commit()
    session.refresh(job)
    _wake.set()
    return job


def wake() -> None:
    """Jobs were added to the session and committed by the caller: start on them."""
    _wake.set()


def find_active(session: Session, kind: str, user_id: int, application_id: int | None = None) -> Job | None:
    query = select(Job).where(Job.kind == kind, Job.user_id == user_id, col(Job.status).in_(ACTIVE))
    if application_id is not None:
        query = query.where(Job.application_id == application_id)
    return session.exec(query).first()


def count_active(session: Session) -> int:
    """Waiting and running jobs of all users."""
    return len(session.exec(select(Job.id).where(col(Job.status).in_(ACTIVE))).all())


def positions(session: Session) -> dict[int, int]:
    """Place of every waiting job in the queue, shared by all users: 1 is the next one."""
    ids = session.exec(select(Job.id).where(Job.status == TaskStatus.PENDING).order_by(Job.id)).all()
    return {job_id: index for index, job_id in enumerate(ids, start=1)}


def _stop_model(job_id: int) -> None:
    with _lock:
        if _running and _running[0] == job_id:
            _running[1].cancel()


def stop_for_application(application_id: int) -> None:
    """The application is being deleted (its jobs go with it): stop the model if it is working on it."""
    with Session(engine) as session:
        ids = session.exec(select(Job.id).where(Job.application_id == application_id)).all()
    for job_id in ids:
        _stop_model(job_id)


def cancel(session: Session, job: Job) -> None:
    """Remove a job. A running one stops the model; an application it was creating is deleted;
    a report it was generating goes back to the previous one. Committed."""
    active = job.status in ACTIVE
    _stop_model(job.id)
    app = session.get(Application, job.application_id) if job.application_id else None
    if active and app is not None and job.new_application:
        delete_applications(session, [app])  # the job goes with it
        return
    if active and app is not None and job.kind == JobKind.REPORT:
        report.restore(app)
        session.add(app)
    session.delete(job)
    session.commit()


def cancel_all(session: Session) -> None:
    """AI turned off: waiting and running jobs are dropped. Applications they were creating stay, with
    their job posting, to be filled in by hand. Not committed."""
    for job in session.exec(select(Job).where(col(Job.status).in_(ACTIVE))).all():
        _stop_model(job.id)
        session.delete(job)


def retry(session: Session, job: Job) -> Job:
    job.status, job.error, job.finished_at = TaskStatus.PENDING, None, None
    if job.kind == JobKind.REPORT and (app := session.get(Application, job.application_id)):
        app.report_status = TaskStatus.PENDING
        session.add(app)
    return enqueue(session, job)


def apply_proposal(session: Session, job: Job) -> None:
    """The user accepts the values the model found for fields already filled. Committed."""
    if job.proposal:
        if job.kind == JobKind.APPLICATION and (app := session.get(Application, job.application_id)):
            apply_changes(session, app, job.proposal)
        elif job.kind == JobKind.PROFILE and (profile := find_profile(session, job.user_id)):
            apply_profile_changes(session, profile, job.proposal)
    session.delete(job)
    session.commit()


def recover(session: Session) -> None:
    """At startup: jobs cut off by a restart run again, old finished jobs go away."""
    for job in session.exec(select(Job).where(Job.status == TaskStatus.RUNNING)).all():
        job.status = TaskStatus.PENDING
        session.add(job)
    session.exec(delete(Job).where(col(Job.status).not_in(ACTIVE), Job.finished_at < now() - timedelta(days=KEEP_DAYS)))
    # A report waiting without a job (e.g. its job was removed with an older version) won't be generated
    queued = select(Job.application_id).where(Job.kind == JobKind.REPORT, col(Job.status).in_(ACTIVE))
    for app in session.exec(select(Application).where(col(Application.report_status).in_(ACTIVE),
                                                      col(Application.id).not_in(queued))).all():
        report.restore(app)
        session.add(app)
    session.commit()


# Running a job: prepare reads what the model needs, the model call runs with no database session open,
# finish saves the result unless the job was cancelled meanwhile

def _split(current: dict, found: dict) -> tuple[dict, dict]:
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


def _prepare(session: Session, job: Job) -> Callable[[], object]:
    if job.kind == JobKind.APPLICATION:
        text = job.source_text or ""
        return lambda: extract_job_fields(text)
    if job.kind == JobKind.PROFILE:
        profile = find_profile(session, job.user_id)
        if profile is None or not profile.cv_text:
            raise LLMError(t("upload_first_cv"))
        cv_text = profile.cv_text
        return lambda: extract_cv_fields(cv_text)
    app = session.get(Application, job.application_id)
    app.report_status = TaskStatus.RUNNING
    session.add(app)
    system, prompt = report.prepare(session, app)
    return lambda: report.ask_model(system, prompt)


def _finish(session: Session, job: Job, result) -> None:
    if job.kind == JobKind.APPLICATION:
        app = session.get(Application, job.application_id)
        fill, job.proposal = _split(app.model_dump(), result)
        # The posting read becomes the saved one, and its link the application's link
        if job.source_text and job.source_text != app.description:
            fill["description"] = job.source_text
        if job.source_url and not app.source_url:
            fill["source_url"] = job.source_url
        apply_changes(session, app, fill)
        if job.then_report and app.skills and not find_active(session, JobKind.REPORT, job.user_id, app.id):
            # Queued now, so it runs after the jobs already waiting; committed with this job's result
            app.report_status = TaskStatus.PENDING
            session.add(Job(user_id=job.user_id, kind=JobKind.REPORT, application_id=app.id))
            _wake.set()
    elif job.kind == JobKind.PROFILE:
        profile = find_profile(session, job.user_id)
        fill, job.proposal = _split(profile.model_dump(), result)
        apply_profile_changes(session, profile, fill)
    else:
        report.save_result(session, session.get(Application, job.application_id), result)
    job.proposal = job.proposal or None


def _fail(session: Session, job: Job, error: str) -> None:
    job.error = error
    if job.kind == JobKind.REPORT and (app := session.get(Application, job.application_id)):
        report.save_error(session, app, error)


def process_next() -> bool:
    """Run the oldest waiting job; False when there is none."""
    global _running
    token = CancelToken()
    with Session(engine) as session:
        job = session.exec(select(Job).where(Job.status == TaskStatus.PENDING).order_by(Job.id).limit(1)).first()
        if job is None:
            return False
        job_id = job.id
        user = session.get(User, job.user_id)
        # Messages and generated text in the user's language
        user_language = user.language if user else "it"
        language = current_language.set(user_language)
        job.status = TaskStatus.RUNNING
        session.add(job)
        try:
            run = _prepare(session, job)
        except LLMError as exc:
            run = None
            job.status, job.error, job.finished_at = TaskStatus.FAILED, str(exc), now()
        session.commit()
    with _lock:
        _running = (job_id, token)
    token_ref = cancel_token.set(token)
    result, error = None, None
    try:
        if run is not None:
            result = run()
    except Cancelled:
        return True
    except LLMError as exc:
        error = str(exc)
    except Exception:
        log.exception("Job %s failed", job_id)
        error = t("task_failed")
    finally:
        with _lock:
            _running = None
        cancel_token.reset(token_ref)
        current_language.reset(language)

    with Session(engine) as session:
        job = session.get(Job, job_id)
        if run is None or job is None or token.cancelled:
            return True
        language = current_language.set(user_language)
        try:
            if error is None:
                _finish(session, job, result)
                job.status = TaskStatus.DONE
            else:
                _fail(session, job, error)
                job.status = TaskStatus.FAILED
            job.finished_at = now()
            session.add(job)
            session.commit()
        finally:
            current_language.reset(language)
    return True


def run_all() -> None:
    """Run every waiting job now (tests, which have no worker thread)."""
    while process_next():
        pass


# Worker thread

def _llm_ready() -> bool:
    with Session(engine) as session:
        if not app_settings.load(session).llm_enabled:
            return False
    llm = check_llm()
    return llm["reachable"] and llm["model_available"]


def _has_pending() -> bool:
    with Session(engine) as session:
        return session.exec(select(Job.id).where(Job.status == TaskStatus.PENDING).limit(1)).first() is not None


def _loop() -> None:
    while not _stop.is_set():
        _wake.clear()
        try:
            # No job starts while an update is installed or a backup restored
            if maintenance.installing() or maintenance.restoring():
                _stop.wait(2)
                continue
            if not _has_pending() or not _llm_ready():
                _wake.wait(POLL_SECONDS)
                continue
            process_next()
        except Exception:
            log.exception("Job worker error")
            _stop.wait(POLL_SECONDS)


def start() -> None:
    global _thread
    with Session(engine) as session:
        recover(session)
    _stop.clear()
    _thread = threading.Thread(target=_loop, name="jobs", daemon=True)
    _thread.start()


def stop() -> None:
    """On shutdown the running job is interrupted and runs again at the next start."""
    _stop.set()
    _wake.set()
    with _lock:
        if _running:
            _running[1].cancel()
    if _thread is not None:
        _thread.join(timeout=10)
