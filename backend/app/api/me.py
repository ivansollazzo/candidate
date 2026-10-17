"""Current user's account: details, preferences, password, recovery key and profile photo."""

from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, Response, UploadFile, status
from fastapi.responses import FileResponse
from sqlmodel import Session

from app.api.uploads import read_upload
from app.db import get_session, save
from app.i18n import t
from app.models import User, UserRole
from app.schemas import MeUpdate, PasswordChange, PasswordConfirm, UserRead
from app.services import app_settings, security
from app.services.users import ensure_unique, remove_avatar, save_avatar

router = APIRouter(prefix="/api/me", tags=["me"])


def _confirm_password(user: User, password: str) -> None:
    if not security.verify_secret(password, user.password_hash):
        raise HTTPException(status.HTTP_403_FORBIDDEN, t("wrong_password"))


@router.get("", response_model=UserRead)
def get_me(user: User = Depends(security.current_user)):
    return user


@router.patch("", response_model=UserRead)
def update_me(payload: MeUpdate, user: User = Depends(security.current_user), session: Session = Depends(get_session)):
    changes = payload.model_dump(exclude_unset=True, exclude_none=True)
    for field in ("username", "email"):
        if field in changes:
            changes[field] = changes[field].lower()
    ensure_unique(session, changes.get("username"), changes.get("email"), exclude_id=user.id)
    for field, value in changes.items():
        setattr(user, field, value)
    return save(session, user)


@router.post("/password", response_model=UserRead)
def change_password(payload: PasswordChange, response: Response, user: User = Depends(security.current_user),
                    session: Session = Depends(get_session)):
    _confirm_password(user, payload.current_password)
    settings = app_settings.load(session)
    security.check_password(payload.new_password, settings)
    user.password_hash = security.hash_secret(payload.new_password)
    # Other open sessions are invalidated; this one continues with a new cookie
    user.session_version += 1
    save(session, user)
    security.start_session(response, user, settings)
    return user


@router.post("/recovery-key")
def new_recovery_key(payload: PasswordConfirm, user: User = Depends(security.current_user),
                     session: Session = Depends(get_session)):
    """Generate a new downloadable recovery key; the old one stops working."""
    _confirm_password(user, payload.password)
    key = security.rotate_recovery_key(user)
    save(session, user)
    return {"recovery_key": key}


@router.put("/avatar", response_model=UserRead)
async def upload_avatar(file: UploadFile = File(...), user: User = Depends(security.current_user),
                        session: Session = Depends(get_session)):
    save_avatar(user, await read_upload(file))
    return save(session, user)


@router.delete("/avatar", response_model=UserRead)
def delete_avatar(user: User = Depends(security.current_user), session: Session = Depends(get_session)):
    remove_avatar(user)
    return save(session, user)


def avatar_response(target: User | None, viewer: User) -> FileResponse:
    if target is None or (target.id != viewer.id and viewer.role != UserRole.ADMIN):
        raise HTTPException(status.HTTP_404_NOT_FOUND, t("user_not_found"))
    if not target.avatar_path or not Path(target.avatar_path).exists():
        raise HTTPException(status.HTTP_404_NOT_FOUND, t("no_avatar"))
    return FileResponse(target.avatar_path, media_type="image/webp", headers={"Cache-Control": "private, no-cache"})


@router.get("/avatar")
def get_avatar(user: User = Depends(security.current_user)):
    return avatar_response(user, user)
