"""The profile: changes from the API and the background jobs, project skills, the CV file."""

import re
from collections.abc import Callable
from pathlib import Path

from sqlmodel import Session

from app.core.i18n import t
from app.features.profile import repository
from app.features.profile.models import Profile
from app.shared.storage import user_dir

# Run in the same transaction when the skills of a user's profile change (registered in main.wire)
_skills_changed: list[Callable[[Session, int], None]] = []


def on_skills_changed(callback: Callable[[Session, int], None]) -> None:
    _skills_changed.append(callback)


def find_profile(session: Session, user_id: int) -> Profile | None:
    return repository.find_by_user(session, user_id)


def get_or_create(session: Session, user_id: int) -> Profile:
    """The user's profile; a new one is added to the session (not committed)."""
    profile = repository.find_by_user(session, user_id)
    if profile is None:
        profile = Profile(user_id=user_id)
        repository.add(session, profile)
    return profile


def skill_key(name: str | None) -> str:
    return " ".join((name or "").lower().split())


def skills_signature(profile: Profile) -> list[tuple[str, int]]:
    """What of the profile a profile match report depends on."""
    return sorted((skill_key(s.get("name")), s.get("level") or 0) for s in profile.skills)


def apply_profile_changes(session: Session, profile: Profile, changes: dict) -> None:
    """Set the given fields and add project skills; changed skills run the registered callbacks. Not committed."""
    before = skills_signature(profile)
    for field, value in changes.items():
        setattr(profile, field, value)
    add_project_skills(profile)
    if skills_signature(profile) != before:
        for callback in _skills_changed:
            callback(session, profile.user_id)
    repository.add(session, profile)


def add_project_skills(profile: Profile) -> bool:
    """Add missing technologies from projects and experiences to skills, without a level; the user sets it."""
    known = {skill["name"].strip().lower() for skill in profile.skills}
    sources = [(project, t("skill_from_project", name=project.get("name") or "")) for project in profile.projects]
    sources += [(job, t("skill_from_experience", name=" · ".join(filter(None, (job.get("role"), job.get("company"))))))
                for job in profile.experiences]
    added = []
    for entry, evidence in sources:
        for tech in entry.get("technologies") or []:
            name = tech.strip()
            if name and name.lower() not in known:
                known.add(name.lower())
                added.append({"name": name, "category": None, "level": None, "evidence": evidence})
    if added:
        profile.skills = [*profile.skills, *added]
    return bool(added)


def store_cv(profile: Profile, filename: str, data: bytes, text: str) -> None:
    """Replace the CV file and its text. Not committed."""
    if profile.cv_path:
        Path(profile.cv_path).unlink(missing_ok=True)
    safe_name = re.sub(r"[^A-Za-z0-9._-]", "_", Path(filename).name)
    path = user_dir(profile.user_id) / f"cv_{safe_name}"
    path.write_bytes(data)
    profile.cv_filename = filename
    profile.cv_path = str(path)
    profile.cv_text = text
