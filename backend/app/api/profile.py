import re
from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from fastapi.responses import FileResponse
from sqlmodel import Session

from app.api.uploads import read_upload
from app.db import get_session, save
from app.i18n import t
from app.models import Profile, User
from app.schemas import ProfileRead, ProfileUpdate
from app.services import security
from app.services.documents import UnsupportedDocument, extract_text
from app.services.users import add_project_skills, find_profile, user_dir

router = APIRouter(prefix="/api/profile", tags=["profile"])


def _get_or_create(session: Session, user: User) -> Profile:
    profile = find_profile(session, user.id)
    return profile if profile is not None else save(session, Profile(user_id=user.id))


@router.get("", response_model=ProfileRead)
def get_profile(user: User = Depends(security.current_user), session: Session = Depends(get_session)):
    profile = _get_or_create(session, user)
    # Checked on every read so profiles saved earlier also get project skills
    return save(session, profile) if add_project_skills(profile) else profile


@router.patch("", response_model=ProfileRead)
def update_profile(payload: ProfileUpdate, user: User = Depends(security.current_user),
                   session: Session = Depends(get_session)):
    profile = _get_or_create(session, user)
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(profile, field, value)
    add_project_skills(profile)
    return save(session, profile)


@router.post("/cv", response_model=ProfileRead)
async def upload_cv(file: UploadFile = File(...), user: User = Depends(security.current_user),
                    session: Session = Depends(get_session)):
    """Store the CV and its text; profile fields are filled by hand or via /api/ai/cv."""
    data = await read_upload(file)
    filename = file.filename or "cv"
    try:
        text = extract_text(filename, data)
    except UnsupportedDocument as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc)) from exc

    profile = _get_or_create(session, user)
    if profile.cv_path:
        Path(profile.cv_path).unlink(missing_ok=True)
    safe_name = re.sub(r"[^A-Za-z0-9._-]", "_", Path(filename).name)
    path = user_dir(user.id) / f"cv_{safe_name}"
    path.write_bytes(data)

    profile.cv_filename = filename
    profile.cv_path = str(path)
    profile.cv_text = text
    return save(session, profile)


@router.get("/cv")
def download_cv(user: User = Depends(security.current_user), session: Session = Depends(get_session)):
    profile = _get_or_create(session, user)
    if not profile.cv_path or not Path(profile.cv_path).exists():
        raise HTTPException(status.HTTP_404_NOT_FOUND, t("no_cv"))
    return FileResponse(profile.cv_path, filename=profile.cv_filename)
