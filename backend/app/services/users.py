"""Shared user operations: username/email uniqueness, profile photo, personal files."""

import io
import shutil
from pathlib import Path

from fastapi import HTTPException, status
from PIL import Image, UnidentifiedImageError
from sqlmodel import Session, func, select

from app.config import get_settings
from app.i18n import t
from app.models import Profile, User, UserRole

AVATAR_SIZE = 256
# Larger images are rejected ("decompression bomb" protection)
Image.MAX_IMAGE_PIXELS = 40_000_000


def ensure_unique(session: Session, username: str | None, email: str | None, exclude_id: int | None = None) -> None:
    for field, value, message in (("username", username, "username_taken"), ("email", email, "email_taken")):
        if value is None:
            continue
        query = select(User).where(getattr(User, field) == value)
        if exclude_id is not None:
            query = query.where(User.id != exclude_id)
        if session.exec(query).first():
            raise HTTPException(status.HTTP_409_CONFLICT, t(message))


def admin_count(session: Session) -> int:
    return session.exec(select(func.count()).select_from(User).where(User.role == UserRole.ADMIN)).one()


def find_profile(session: Session, user_id: int) -> Profile | None:
    return session.exec(select(Profile).where(Profile.user_id == user_id)).first()


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


def user_dir(user_id: int) -> Path:
    """User's file directory (CV, profile photo)."""
    folder = get_settings().upload_dir / f"user_{user_id}"
    folder.mkdir(parents=True, exist_ok=True)
    return folder


def save_avatar(user: User, data: bytes) -> None:
    """Resize the photo and save it as WebP; re-encoding strips metadata and any embedded payload."""
    try:
        with Image.open(io.BytesIO(data)) as image:
            image.load()
            image = image.convert("RGBA") if image.mode in ("RGBA", "LA", "P") else image.convert("RGB")
            # Centered square crop
            side = min(image.size)
            left, top = (image.width - side) // 2, (image.height - side) // 2
            image = image.crop((left, top, left + side, top + side)).resize((AVATAR_SIZE, AVATAR_SIZE))
            path = user_dir(user.id) / "avatar.webp"
            image.save(path, "WEBP", quality=85)
    except (UnidentifiedImageError, Image.DecompressionBombError, OSError) as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, t("invalid_image")) from exc
    user.avatar_path = str(path)


def remove_avatar(user: User) -> None:
    if user.avatar_path:
        Path(user.avatar_path).unlink(missing_ok=True)
    user.avatar_path = None


def remove_files(user_id: int) -> None:
    shutil.rmtree(get_settings().upload_dir / f"user_{user_id}", ignore_errors=True)
