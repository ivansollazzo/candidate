"""Applications: ownership, status history, changes from the API and the background jobs, deletion with files."""

from collections.abc import Callable
from datetime import date

from fastapi import HTTPException, status
from sqlmodel import Session

from app.core.i18n import t
from app.features.applications import repository
from app.features.applications.attachments import attachments_dir, remove_attachments
from app.features.applications.models import Application, ApplicationEvent, EventType
from app.features.applications.schemas import ApplicationListItem
from app.features.background_jobs import service as jobs
from app.features.background_jobs.models import Job, TaskStatus

# Fields of the position a profile match report depends on
POSITION_FIELDS = ("skills", "requirements", "nice_to_have")

# Callbacks registered in main.wire, run in the same transaction
_position_changed: list[Callable[[Session, Application], None]] = []
_filled: list[Callable[[Session, Application, Job], None]] = []


def on_position_changed(callback: Callable[[Session, Application], None]) -> None:
    """When skills, requirements or nice-to-have of an application change."""
    _position_changed.append(callback)


def on_filled(callback: Callable[[Session, Application, Job], None]) -> None:
    """When a background job has filled an application from its job posting."""
    _filled.append(callback)


def filled(session: Session, app: Application, job: Job) -> None:
    for callback in _filled:
        callback(session, app, job)


def get_owned(session: Session, application_id: int, user) -> Application:
    """Fetch the user's application; other users' applications look nonexistent."""
    app = repository.get(session, application_id)
    if app is None or app.user_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, t("application_not_found"))
    return app


def list_items(session: Session, user_id: int) -> list[ApplicationListItem]:
    """The list with the date of the last event and a summary of the profile match report."""
    items = []
    for app, last_on in repository.list_with_last_event(session, user_id):
        report = app.report if app.report_status == TaskStatus.DONE and app.report else None
        items.append(ApplicationListItem.model_validate(app).model_copy(update={
            "last_event_on": last_on,
            "match_score": report.get("score") if report else None,
            "report_stale": bool(report) and app.report_stale,
            "missing_skills": [s["skill"] for s in (report or {}).get("skills", [])
                               if s.get("status") == "missing" and s.get("kind") != "soft"],
        }))
    return items


def change_status(session: Session, app: Application, new_status: str) -> None:
    """Set the status, keeping every change in the history."""
    if new_status == app.status:
        return
    repository.add(session, ApplicationEvent(
        application_id=app.id,
        type=EventType.STATUS_CHANGE,
        occurred_on=date.today(),
        completed=True,
        # Statuses stored as codes ("applied>interview"); the frontend localizes them
        title=f"{app.status}>{new_status}",
    ))
    app.status = new_status


def apply_changes(session: Session, app: Application, changes: dict) -> None:
    """Set the given fields; a changed position runs the registered callbacks. Not committed."""
    changes = dict(changes)
    if new_status := changes.pop("status", None):
        change_status(session, app, new_status)
    position_changed = any(field in changes and changes[field] != getattr(app, field) for field in POSITION_FIELDS)
    for field, value in changes.items():
        setattr(app, field, value)
    if position_changed:
        for callback in _position_changed:
            callback(session, app)
    repository.add(session, app)


def delete_applications(session: Session, apps: list[Application]) -> None:
    """Delete and commit; attached files go too, so they don't take up space."""
    folders = [attachments_dir(app) for app in apps]
    for app in apps:
        jobs.stop_for_application(app.id)
        repository.delete(session, app)
    session.commit()
    remove_attachments(folders)
