"""Users and their credentials; preferences columns are written by the users feature."""

from datetime import datetime
from enum import StrEnum
from typing import Any

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB
from sqlmodel import Field, SQLModel

from app.shared.database import bool_field, int_field, timestamp


class UserRole(StrEnum):
    ADMIN = "admin"  # manages users, AI features and security policy
    USER = "user"


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
    # Sort order of the applications list
    application_sort: str = Field(default="applied", sa_type=sa.String(10),
                                  sa_column_kwargs={"server_default": "applied"})
    # Status shown in the applications list ("all" or an ApplicationStatus)
    application_filter: str = Field(default="all", sa_type=sa.String(20), sa_column_kwargs={"server_default": "all"})
    # New applications filled by the AI also get their compatibility report
    report_after_fill: bool = bool_field(False)
    # Widgets of the overview, in order: [{"id": ..., "size": "half" | "full"}]; null for the default layout
    overview_layout: list[dict] | None = Field(default=None, sa_column=sa.Column(JSONB, nullable=True))
    # False until the user completes the onboarding wizard
    onboarded: bool = bool_field(False)
    avatar_path: str | None = None

    # Bumped on every password change to invalidate older sessions
    session_version: int = int_field(0)
    failed_logins: int = int_field(0)
    locked_until: datetime | None = Field(default=None, sa_type=sa.DateTime(timezone=True))

    created_at: datetime = timestamp()
    updated_at: datetime = timestamp(onupdate=True)

    @property
    def has_avatar(self) -> bool:
        return bool(self.avatar_path)


def owner_field(unique: bool = False) -> Any:
    # Owner of a row of another feature (profile, application); nullable as in the first schema
    return Field(default=None, sa_column=sa.Column(
        sa.ForeignKey("app_user.id", ondelete="CASCADE"), nullable=True, index=True, unique=unique))
