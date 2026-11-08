"""The thread that runs the queued jobs, one at a time: prepare reads what the model needs, the model call runs
with no database session open, finish saves the result unless the job was cancelled meanwhile."""

import logging
import threading

from sqlmodel import Session

from app.core.i18n import current_language, t
from app.features.auth import repository as auth_repository
from app.features.background_jobs import repository, service
from app.features.background_jobs.models import TaskStatus
from app.features.settings import service as settings_service
from app.shared import maintenance
from app.shared.database import engine
from app.shared.llm import Cancelled, CancelToken, LLMError, cancel_token, check_llm

log = logging.getLogger(__name__)

# Seconds between checks while waiting for jobs, the model or an update
POLL_SECONDS = 5

_stop = threading.Event()
_thread: threading.Thread | None = None


def process_next() -> bool:
    """Run the oldest waiting job; False when there is none."""
    token = CancelToken()
    with Session(engine) as session:
        job = repository.next_pending(session)
        if job is None:
            return False
        job_id = job.id
        user = auth_repository.get(session, job.user_id)
        # Messages and generated text in the user's language
        user_language = user.language if user else "it"
        language = current_language.set(user_language)
        job.status = TaskStatus.RUNNING
        repository.add(session, job)
        try:
            run = service.handler(job.kind).prepare(session, job)
        except LLMError as exc:
            run = None
            job.status, job.error, job.finished_at = TaskStatus.FAILED, str(exc), service.now()
        session.commit()
    service.set_running(job_id, token)
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
        service.set_running(None)
        cancel_token.reset(token_ref)
        current_language.reset(language)

    with Session(engine) as session:
        job = repository.get(session, job_id)
        if run is None or job is None or token.cancelled:
            return True
        language = current_language.set(user_language)
        try:
            kind_handler = service.handler(job.kind)
            if error is None:
                kind_handler.finish(session, job, result)
                job.proposal = job.proposal or None
                job.status = TaskStatus.DONE
            else:
                job.error = error
                kind_handler.fail(session, job, error)
                job.status = TaskStatus.FAILED
            job.finished_at = service.now()
            repository.add(session, job)
            session.commit()
        finally:
            current_language.reset(language)
    return True


def run_all() -> None:
    """Run every waiting job now (tests, which have no worker thread)."""
    while process_next():
        pass


def _llm_ready() -> bool:
    with Session(engine) as session:
        if not settings_service.load(session).llm_enabled:
            return False
    llm = check_llm()
    return llm["reachable"] and llm["model_available"]


def _has_pending() -> bool:
    with Session(engine) as session:
        return repository.next_pending(session) is not None


def _loop() -> None:
    while not _stop.is_set():
        service.wake_event.clear()
        try:
            # No job starts while an update is installed or a backup restored
            if maintenance.installing() or maintenance.restoring():
                _stop.wait(2)
                continue
            if not _has_pending() or not _llm_ready():
                service.wake_event.wait(POLL_SECONDS)
                continue
            process_next()
        except Exception:
            log.exception("Job worker error")
            _stop.wait(POLL_SECONDS)


def start() -> None:
    global _thread
    with Session(engine) as session:
        service.recover(session)
    _stop.clear()
    _thread = threading.Thread(target=_loop, name="jobs", daemon=True)
    _thread.start()


def stop() -> None:
    """On shutdown the running job is interrupted and runs again at the next start."""
    _stop.set()
    service.wake_event.set()
    service.stop_model()
    if _thread is not None:
        _thread.join(timeout=10)
