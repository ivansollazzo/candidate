"""Filling an application from its job posting, as a background job."""

from sqlmodel import Session

from app.features.applications import repository
from app.features.applications.extraction import extract_job_fields
from app.features.applications.service import apply_changes, delete_applications, filled
from app.features.background_jobs.models import Job
from app.features.background_jobs.service import JobHandler, split_result


class ApplicationFill(JobHandler):
    def prepare(self, session: Session, job: Job):
        text = job.source_text or ""
        return lambda: extract_job_fields(text)

    def finish(self, session: Session, job: Job, result) -> None:
        app = repository.get(session, job.application_id)
        fill, job.proposal = split_result(app.model_dump(), result)
        # The posting read becomes the saved one, and its link the application's link
        if job.source_text and job.source_text != app.description:
            fill["description"] = job.source_text
        if job.source_url and not app.source_url:
            fill["source_url"] = job.source_url
        apply_changes(session, app, fill)
        filled(session, app, job)

    def cancel(self, session: Session, job: Job) -> bool:
        """Cancelling the job that creates an application deletes the application, and the job with it."""
        app = repository.get(session, job.application_id) if job.application_id else None
        if app is not None and job.new_application:
            delete_applications(session, [app])
            return True
        return False

    def accept(self, session: Session, job: Job) -> None:
        if app := repository.get(session, job.application_id):
            apply_changes(session, app, job.proposal)

    def title(self, session: Session, job: Job) -> str | None:
        app = repository.get(session, job.application_id) if job.application_id else None
        return app.title if app else None
