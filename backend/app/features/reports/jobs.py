"""Generating a profile match report, as a background job."""

from sqlmodel import Session

from app.features.applications import repository as applications_repository
from app.features.background_jobs.models import Job, TaskStatus
from app.features.background_jobs.service import JobHandler
from app.features.reports import repository
from app.features.reports.service import (
    ask_model,
    prepare,
    restore,
    save_error,
    save_result,
)


class ReportGeneration(JobHandler):
    def prepare(self, session: Session, job: Job):
        app = applications_repository.get(session, job.application_id)
        app.report_status = TaskStatus.RUNNING
        applications_repository.add(session, app)
        system, prompt = prepare(session, app)
        return lambda: ask_model(system, prompt)

    def finish(self, session: Session, job: Job, result) -> None:
        save_result(session, applications_repository.get(session, job.application_id), result)

    def fail(self, session: Session, job: Job, error: str) -> None:
        if app := applications_repository.get(session, job.application_id):
            save_error(session, app, error)

    def cancel(self, session: Session, job: Job) -> bool:
        """A report that won't be generated goes back to the previous one."""
        if app := applications_repository.get(session, job.application_id):
            restore(app)
            applications_repository.add(session, app)
        return False

    def retry(self, session: Session, job: Job) -> None:
        if app := applications_repository.get(session, job.application_id):
            app.report_status = TaskStatus.PENDING
            applications_repository.add(session, app)

    def recover(self, session: Session) -> None:
        # A report waiting without a job won't be generated
        for app in repository.waiting_without_job(session):
            restore(app)
            applications_repository.add(session, app)

    def title(self, session: Session, job: Job) -> str | None:
        app = applications_repository.get(session, job.application_id)
        return app.title if app else None
