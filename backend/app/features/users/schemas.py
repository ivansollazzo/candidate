from typing import Annotated, Literal

from pydantic import BaseModel, Field, field_validator

from app.features.applications.models import ApplicationStatus
from app.features.auth.schemas import (
    WIDGETS,
    Email,
    Language,
    OverviewWidget,
    Role,
    Secret,
    Username,
)

Theme = Literal["light", "dark", "system"]


ApplicationSort = Literal["applied", "status", "name", "event"]


ApplicationFilter = Literal["all"] | ApplicationStatus


class MeUpdate(BaseModel):
    username: Username | None = None
    email: Email | None = None
    language: Language | None = None
    theme: Theme | None = None
    application_sort: ApplicationSort | None = None
    application_filter: ApplicationFilter | None = None
    report_after_fill: bool | None = None
    # An empty list is a valid layout; reset_overview goes back to the default one
    overview_layout: Annotated[list[OverviewWidget], Field(max_length=len(WIDGETS))] | None = None
    reset_overview: bool | None = None
    onboarded: bool | None = None

    @field_validator("overview_layout")
    @classmethod
    def _unique_widgets(cls, layout):
        if layout is not None and len({w.id for w in layout}) != len(layout):
            raise ValueError("Each widget can appear only once")
        return layout


class UserCreate(BaseModel):
    username: Username
    email: Email
    password: Secret
    role: Role = "user"
    language: Language = "it"


class UserUpdate(BaseModel):
    username: Username | None = None
    email: Email | None = None
    role: Role | None = None
    password: Secret | None = None
