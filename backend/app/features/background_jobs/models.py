"""Queue of background LLM jobs."""

from datetime import datetime
from enum import StrEnum

import sqlalchemy as sa
from sqlmodel import Field, SQLModel

from app.shared.database import bool_field, json_object, timestamp


class TaskStatus(StrEnum):
    """Status of a background job and of the compatibility report it generates."""

    PENDING = "pending"
    RUNNING = "running"
    DONE = "done"
    FAILED = "failed"


class JobKind(StrEnum):
    APPLICATION = "application"  # fill an application from its job posting
    PROFILE = "profile"  # fill the profile from the CV
    REPORT = "report"  # compatibility report of an application


class Job(SQLModel, table=True):
    """Background LLM operation, run one at a time in order of creation (see background_jobs/worker.py).
    Finished jobs stay listed until the user dismisses them."""

    id: int | None = Field(default=None, primary_key=True)
    user_id: int = Field(sa_column=sa.Column(sa.ForeignKey("app_user.id", ondelete="CASCADE"), nullable=False,
                                             index=True))
    kind: str = Field(sa_type=sa.String(20))
    application_id: int | None = Field(default=None, sa_column=sa.Column(
        sa.ForeignKey("application.id", ondelete="CASCADE"), nullable=True, index=True))
    status: str = Field(default=TaskStatus.PENDING, sa_type=sa.String(20), index=True)
    # The application was created by this job: cancelling it before it is filled deletes the application
    new_application: bool = bool_field(False)
    # Once the application is filled, queue its compatibility report
    then_report: bool = bool_field(False)
    # Job posting to read, and the link it came from
    source_text: str | None = Field(default=None, sa_type=sa.Text)
    source_url: str | None = None
    # Values found by the model for fields the user had already filled: applied only if the user confirms
    proposal: dict | None = json_object()
    error: str | None = Field(default=None, sa_type=sa.Text)
    created_at: datetime = timestamp()
    finished_at: datetime | None = Field(default=None, sa_type=sa.DateTime(timezone=True))
