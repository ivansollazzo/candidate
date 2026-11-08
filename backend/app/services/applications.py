"""Changes to applications shared by the API and the background jobs."""

from datetime import date

from sqlmodel import Session

from app.models import Application, ApplicationEvent, EventType, TaskStatus
from app.services.attachments import attachments_dir, remove_attachments

# The compatibility report depends on these fields of the position
REPORT_FIELDS = ("skills", "requirements", "nice_to_have")


def change_status(session: Session, app: Application, new_status: str) -> None:
    """Set the status, keeping every change in the history."""
    if new_status == app.status:
        return
    session.add(ApplicationEvent(
        application_id=app.id,
        type=EventType.STATUS_CHANGE,
        occurred_on=date.today(),
        completed=True,
        # Statuses stored as codes ("applied>interview"); the frontend localizes them
        title=f"{app.status}>{new_status}",
    ))
    app.status = new_status


def apply_changes(session: Session, app: Application, changes: dict) -> None:
    """Set the given fields; a changed position marks the report as stale. Not committed."""
    changes = dict(changes)
    if new_status := changes.pop("status", None):
        change_status(session, app, new_status)
    if app.report_status == TaskStatus.DONE and any(
        field in changes and changes[field] != getattr(app, field) for field in REPORT_FIELDS
    ):
        app.report_stale = True
    for field, value in changes.items():
        setattr(app, field, value)
    session.add(app)


def delete_applications(session: Session, apps: list[Application]) -> None:
    """Delete and commit; attached files go too, so they don't take up space."""
    from app.services import (
        jobs,  # jobs fill applications: imported here to avoid a cycle
    )

    folders = [attachments_dir(app) for app in apps]
    for app in apps:
        jobs.stop_for_application(app.id)
        session.delete(app)
    session.commit()
    remove_attachments(folders)
