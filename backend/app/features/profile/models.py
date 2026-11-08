from datetime import datetime

import sqlalchemy as sa
from sqlmodel import Field, SQLModel

from app.features.auth.models import owner_field
from app.shared.database import json_list, timestamp


class Profile(SQLModel, table=True):
    """Personal profile (one per user)."""

    id: int | None = Field(default=None, primary_key=True)
    user_id: int | None = owner_field(unique=True)
    full_name: str | None = None
    email: str | None = None
    phone: str | None = None
    location: str | None = None
    headline: str | None = None
    summary: str | None = Field(default=None, sa_type=sa.Text)
    years_of_experience: float | None = None
    # Shapes defined in profile/schemas.py (CVLink, CVSkill, CVExperience, ...)
    links: list[dict] = json_list()
    skills: list[dict] = json_list()
    experiences: list[dict] = json_list()
    education: list[dict] = json_list()
    projects: list[dict] = json_list()
    certifications: list[dict] = json_list()
    languages: list[dict] = json_list()

    cv_filename: str | None = None
    cv_path: str | None = None
    cv_text: str | None = Field(default=None, sa_type=sa.Text)

    created_at: datetime = timestamp()
    updated_at: datetime = timestamp(onupdate=True)
