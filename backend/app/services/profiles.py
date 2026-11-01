"""Changes to the profile shared by the API and the background jobs."""

from sqlmodel import Session

from app.models import Profile
from app.services.report import mark_stale, profile_skills
from app.services.users import add_project_skills


def apply_profile_changes(session: Session, profile: Profile, changes: dict) -> None:
    """Set the given fields and add project skills; changed skills mark the reports as stale. Not committed."""
    skills_before = profile_skills(profile)
    for field, value in changes.items():
        setattr(profile, field, value)
    add_project_skills(profile)
    if profile_skills(profile) != skills_before:
        mark_stale(session, profile.user_id)
    session.add(profile)
