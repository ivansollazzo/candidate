from datetime import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field


class PasswordPolicy(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    password_min_length: int
    password_require_uppercase: bool
    password_require_digit: bool
    password_require_symbol: bool


Username = Annotated[str, Field(min_length=3, max_length=50, pattern=r"^[A-Za-z0-9._-]+$")]


Email = Annotated[str, Field(max_length=255, pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$")]


Role = Literal["admin", "user"]


Language = Literal["it", "en"]


# Widgets the overview can show
WIDGETS = ("counts", "calendar", "events", "recent", "profile", "weekly", "top_matches", "stale_reports",
           "missing_skills")


class OverviewWidget(BaseModel):
    id: Literal[WIDGETS]
    size: Literal["half", "full"] = "half"


# Upper bound so we never hash huge inputs
Secret = Annotated[str, Field(max_length=256)]


class UserRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    username: str
    email: str
    role: str
    language: str
    theme: str
    application_sort: str
    application_filter: str
    report_after_fill: bool
    overview_layout: list[OverviewWidget] | None
    onboarded: bool
    has_avatar: bool
    created_at: datetime
    updated_at: datetime


class UserWithKey(BaseModel):
    """Newly created or recovered user, with the recovery key to show only once."""

    user: UserRead
    recovery_key: str


class SetupRequest(BaseModel):
    username: Username
    email: Email
    password: Secret
    language: Language = "it"


class LoginRequest(BaseModel):
    username: Annotated[str, Field(max_length=50)]
    password: Secret


class ResetRequest(BaseModel):
    username: Annotated[str, Field(max_length=50)]
    recovery_key: Secret
    new_password: Secret


class AuthStatus(BaseModel):
    setup_required: bool
    password_policy: PasswordPolicy


class PasswordChange(BaseModel):
    current_password: Secret
    new_password: Secret


class PasswordConfirm(BaseModel):
    password: Secret
