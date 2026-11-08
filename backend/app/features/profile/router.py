from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from fastapi.responses import FileResponse
from sqlmodel import Session

from app.core.i18n import t
from app.features.auth.dependencies import current_user
from app.features.auth.models import User
from app.features.background_jobs import service as jobs
from app.features.background_jobs.models import Job, JobKind
from app.features.background_jobs.schemas import JobRead
from app.features.profile.models import Profile
from app.features.profile.schemas import ProfileRead, ProfileUpdate
from app.features.profile.service import (
    apply_profile_changes,
    find_profile,
    get_or_create,
    store_cv,
)
from app.features.settings.service import require_llm
from app.shared.database import get_session, save
from app.shared.documents import UnsupportedDocument, extract_text
from app.shared.storage import read_upload

router = APIRouter(prefix="/api/profile", tags=["profile"])


@router.get("", response_model=ProfileRead)
def get_profile(user: User = Depends(current_user), session: Session = Depends(get_session)):
    """Read only: a user who never saved the profile gets an empty one (id null), created by the first write."""
    profile = find_profile(session, user.id)
    if profile is None:
        return ProfileRead.model_validate(Profile(user_id=user.id)).model_copy(update={"updated_at": None})
    return profile


@router.patch("", response_model=ProfileRead)
def update_profile(payload: ProfileUpdate, user: User = Depends(current_user),
                   session: Session = Depends(get_session)):
    profile = get_or_create(session, user.id)
    apply_profile_changes(session, profile, payload.model_dump(exclude_unset=True))
    return save(session, profile)


@router.post("/fills", response_model=JobRead, status_code=status.HTTP_202_ACCEPTED)
def fill_from_cv(user: User = Depends(current_user), session: Session = Depends(get_session)):
    """Fill the profile from the uploaded CV in the background. Empty fields are filled when the job is
    done; values for filled fields are proposed (accepted with POST /api/jobs/{id}/accept)."""
    require_llm(session)
    profile = find_profile(session, user.id)
    if profile is None or not profile.cv_text:
        raise HTTPException(status.HTTP_409_CONFLICT, t("upload_first_cv"))
    if jobs.find_active(session, JobKind.PROFILE, user.id):
        raise HTTPException(status.HTTP_409_CONFLICT, t("job_running"))
    return jobs.enqueue(session, Job(user_id=user.id, kind=JobKind.PROFILE))


@router.put("/cv", response_model=ProfileRead)
async def upload_cv(file: UploadFile = File(...), user: User = Depends(current_user),
                    session: Session = Depends(get_session)):
    """Store the CV and its text; profile fields are filled by hand or via POST /api/profile/fills."""
    data = await read_upload(file)
    filename = file.filename or "cv"
    try:
        text = extract_text(filename, data)
    except UnsupportedDocument as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc)) from exc

    profile = get_or_create(session, user.id)
    store_cv(profile, filename, data, text)
    return save(session, profile)


@router.get("/cv")
def download_cv(user: User = Depends(current_user), session: Session = Depends(get_session)):
    profile = find_profile(session, user.id)
    if profile is None or not profile.cv_path or not Path(profile.cv_path).exists():
        raise HTTPException(status.HTTP_404_NOT_FOUND, t("no_cv"))
    return FileResponse(profile.cv_path, filename=profile.cv_filename)
