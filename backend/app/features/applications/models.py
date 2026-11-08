"""Applications with the job posting fields, their events and attachments. The report columns are written only by the reports feature."""

from datetime import date, datetime, time
from enum import StrEnum

import sqlalchemy as sa
from sqlmodel import Field, Relationship, SQLModel

from app.features.auth.models import owner_field
from app.shared.database import bool_field, json_list, json_object, timestamp


class ApplicationStatus(StrEnum):
    APPLIED = "applied"
    INTERVIEW = "interview"
    OFFER = "offer"
    INACTIVE = "inactive"
    REJECTED = "rejected"
    COMPLETED = "completed"


class EventType(StrEnum):
    STATUS_CHANGE = "status_change"
    INTERVIEW = "interview"
    CALL = "call"
    EMAIL = "email"
    FOLLOW_UP = "follow_up"
    NOTE = "note"


class Application(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    user_id: int | None = owner_field()

    # Fields extracted from the job posting (editable by hand)
    title: str | None = None
    company: str | None = None
    location: str | None = None
    work_mode: str | None = None  # onsite / hybrid / remote
    contract_type: str | None = None
    seniority: str | None = None
    # Expected salary as free text (amount or range), plus period and gross/net
    salary: str | None = None
    salary_period: str | None = Field(default=None, sa_type=sa.String(10))  # annual / monthly / daily / hourly
    salary_basis: str | None = Field(default=None, sa_type=sa.String(10))  # gross / net
    responsibilities: list[str] = json_list()
    requirements: list[str] = json_list()
    nice_to_have: list[str] = json_list()
    benefits: list[str] = json_list()
    # [{"name": "Python", "importance": "required" | "nice_to_have"}]
    skills: list[dict] = json_list()
    languages: list[str] = json_list()
    education_required: str | None = None
    experience_years_min: float | None = None

    # Job posting text, used only for LLM field filling
    description: str | None = Field(default=None, sa_type=sa.Text)
    source_url: str | None = None
    contact_name: str | None = None
    contact_email: str | None = None

    status: str = Field(default=ApplicationStatus.APPLIED, sa_type=sa.String(20), index=True)
    # New applications count as already sent: date defaults to today, editable
    applied_on: date | None = Field(default_factory=date.today)
    notes: str | None = Field(default=None, sa_type=sa.Text)

    # LLM-generated compatibility report (schemas.Report), generated on request
    report: dict | None = json_object()
    report_status: str | None = Field(default=None, sa_type=sa.String(20))
    report_stale: bool = bool_field(False)

    created_at: datetime = timestamp()
    updated_at: datetime = timestamp(onupdate=True)

    @property
    def has_description(self) -> bool:
        return bool(self.description)

    events: list["ApplicationEvent"] = Relationship(
        back_populates="application",
        sa_relationship_kwargs={"cascade": "all, delete-orphan", "order_by": "ApplicationEvent.occurred_on"},
    )
    attachments: list["ApplicationAttachment"] = Relationship(
        back_populates="application",
        sa_relationship_kwargs={"cascade": "all, delete-orphan", "order_by": "ApplicationAttachment.id"},
    )


class ApplicationEvent(SQLModel, table=True):
    """Application event: scheduled (interview, follow-up...) or past (notes, status changes)."""

    __tablename__ = "application_event"

    id: int | None = Field(default=None, primary_key=True)
    application_id: int = Field(
        sa_column=sa.Column(sa.ForeignKey("application.id", ondelete="CASCADE"), nullable=False, index=True)
    )
    type: str = Field(default=EventType.NOTE, sa_type=sa.String(20))
    occurred_on: date
    # Optional start time (e.g. interview at 15:00)
    starts_at: time | None = None
    # Optional end time, only with a start time
    ends_at: time | None = None
    title: str
    details: str | None = Field(default=None, sa_type=sa.Text)
    completed: bool = Field(default=False, sa_column_kwargs={"server_default": sa.false()})
    created_at: datetime = timestamp()

    application: Application | None = Relationship(back_populates="events")


class ApplicationAttachment(SQLModel, table=True):
    """File attached to an application; its file on disk goes away with the application."""

    __tablename__ = "application_attachment"

    id: int | None = Field(default=None, primary_key=True)
    application_id: int = Field(
        sa_column=sa.Column(sa.ForeignKey("application.id", ondelete="CASCADE"), nullable=False, index=True)
    )
    # Original name, shown in the UI and used for downloads
    filename: str = Field(sa_type=sa.String(255))
    # Name on disk, inside the application's attachment folder
    stored_name: str = Field(sa_type=sa.String(64))
    content_type: str | None = Field(default=None, sa_type=sa.String(255))
    size: int
    created_at: datetime = timestamp()

    application: Application | None = Relationship(back_populates="attachments")
