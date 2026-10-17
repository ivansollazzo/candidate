from datetime import date, datetime, time, timezone
from enum import StrEnum
from typing import Any

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB
from sqlmodel import Field, Relationship, SQLModel


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class ApplicationStatus(StrEnum):
    APPLIED = "applied"
    INTERVIEW = "interview"
    OFFER = "offer"
    REJECTED = "rejected"
    COMPLETED = "completed"


class UserRole(StrEnum):
    ADMIN = "admin"  # manages users, AI features and security policy
    USER = "user"


class TaskStatus(StrEnum):
    """Status of LLM-generated advice."""

    PENDING = "pending"
    RUNNING = "running"
    DONE = "done"
    FAILED = "failed"


class EventType(StrEnum):
    STATUS_CHANGE = "status_change"
    INTERVIEW = "interview"
    CALL = "call"
    EMAIL = "email"
    FOLLOW_UP = "follow_up"
    NOTE = "note"


def _json_list() -> Any:
    return Field(default_factory=list, sa_column=sa.Column(JSONB, nullable=False, server_default="[]"))


def _json_obj_nullable() -> Any:
    return Field(default=None, sa_column=sa.Column(JSONB, nullable=True))


def _timestamp(onupdate: bool = False) -> Any:
    return Field(
        default_factory=utcnow,
        sa_column=sa.Column(
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
            onupdate=utcnow if onupdate else None,
        ),
    )


def _int(default: int) -> Any:
    return Field(default=default, sa_column_kwargs={"server_default": str(default)})


def _bool(default: bool) -> Any:
    return Field(default=default, sa_column_kwargs={"server_default": sa.true() if default else sa.false()})


class AppSettings(SQLModel, table=True):
    """System settings (single row), editable by the admin."""

    __tablename__ = "app_settings"

    id: int | None = Field(default=None, primary_key=True)
    llm_enabled: bool = _bool(True)
    # auto, cuda, rocm, vulkan, cpu; read by the llm service
    llm_accelerator: str = Field(default="auto", sa_type=sa.String(10), sa_column_kwargs={"server_default": "auto"})

    # Security policy
    password_min_length: int = _int(10)
    password_require_uppercase: bool = _bool(True)
    password_require_digit: bool = _bool(True)
    password_require_symbol: bool = _bool(False)
    session_hours: int = _int(12)
    # 0 = no lockout after failed attempts
    max_login_attempts: int = _int(5)
    lockout_minutes: int = _int(15)
    # Session signing key, generated on first run
    secret_key: str | None = Field(default=None, sa_type=sa.String(128))

    updated_at: datetime = _timestamp(onupdate=True)


class User(SQLModel, table=True):
    """App user; each user sees only their own applications and profile."""

    __tablename__ = "app_user"  # "user" is a reserved word in PostgreSQL

    id: int | None = Field(default=None, primary_key=True)
    # Stored lowercase so login is case-insensitive
    username: str = Field(sa_type=sa.String(50), unique=True, index=True)
    email: str = Field(sa_type=sa.String(255), unique=True)
    password_hash: str = Field(sa_type=sa.String(255))
    # The recovery key is shown only once; only its hash is stored
    recovery_key_hash: str = Field(sa_type=sa.String(255))
    role: str = Field(default=UserRole.USER, sa_type=sa.String(10))

    # Preferences
    language: str = Field(default="it", sa_type=sa.String(5), sa_column_kwargs={"server_default": "it"})
    theme: str = Field(default="system", sa_type=sa.String(10), sa_column_kwargs={"server_default": "system"})
    # False until the user completes the onboarding wizard
    onboarded: bool = _bool(False)
    avatar_path: str | None = None

    # Bumped on every password change to invalidate older sessions
    session_version: int = _int(0)
    failed_logins: int = _int(0)
    locked_until: datetime | None = Field(default=None, sa_type=sa.DateTime(timezone=True))

    created_at: datetime = _timestamp()
    updated_at: datetime = _timestamp(onupdate=True)

    @property
    def has_avatar(self) -> bool:
        return bool(self.avatar_path)


def _owner(unique: bool = False) -> Any:
    # Nullable only for data created before users existed; claimed by the first admin
    return Field(default=None, sa_column=sa.Column(
        sa.ForeignKey("app_user.id", ondelete="CASCADE"), nullable=True, index=True, unique=unique))


class Profile(SQLModel, table=True):
    """Personal profile (one per user)."""

    id: int | None = Field(default=None, primary_key=True)
    user_id: int | None = _owner(unique=True)
    full_name: str | None = None
    email: str | None = None
    phone: str | None = None
    location: str | None = None
    headline: str | None = None
    summary: str | None = Field(default=None, sa_type=sa.Text)
    years_of_experience: float | None = None
    # Shapes defined in app.schemas (CVLink, CVSkill, CVExperience, ...)
    links: list[dict] = _json_list()
    skills: list[dict] = _json_list()
    experiences: list[dict] = _json_list()
    education: list[dict] = _json_list()
    projects: list[dict] = _json_list()
    certifications: list[dict] = _json_list()
    languages: list[dict] = _json_list()

    cv_filename: str | None = None
    cv_path: str | None = None
    cv_text: str | None = Field(default=None, sa_type=sa.Text)

    created_at: datetime = _timestamp()
    updated_at: datetime = _timestamp(onupdate=True)


class Application(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    user_id: int | None = _owner()

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
    responsibilities: list[str] = _json_list()
    requirements: list[str] = _json_list()
    nice_to_have: list[str] = _json_list()
    benefits: list[str] = _json_list()
    # [{"name": "Python", "importance": "required" | "nice_to_have"}]
    skills: list[dict] = _json_list()
    languages: list[str] = _json_list()
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

    # LLM-generated advice on the skill gap
    advice: dict | None = _json_obj_nullable()
    advice_status: str | None = Field(default=None, sa_type=sa.String(20))

    created_at: datetime = _timestamp()
    updated_at: datetime = _timestamp(onupdate=True)

    @property
    def has_description(self) -> bool:
        return bool(self.description)

    events: list["ApplicationEvent"] = Relationship(
        back_populates="application",
        sa_relationship_kwargs={"cascade": "all, delete-orphan", "order_by": "ApplicationEvent.occurred_on"},
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
    title: str
    details: str | None = Field(default=None, sa_type=sa.Text)
    completed: bool = Field(default=False, sa_column_kwargs={"server_default": sa.false()})
    created_at: datetime = _timestamp()

    application: Application | None = Relationship(back_populates="events")
