"""The current user's account (details, preferences, profile photo) and user management, admin only."""

from fastapi import (
    APIRouter,
    Depends,
    File,
    HTTPException,
    Response,
    UploadFile,
    status,
)
from sqlmodel import Session

from app.core.i18n import t
from app.features.auth import repository as auth_repository
from app.features.auth import service as security
from app.features.auth.dependencies import admin_user, current_user
from app.features.auth.models import User, UserRole
from app.features.auth.schemas import UserRead, UserWithKey
from app.features.settings import service as settings_service
from app.features.users.schemas import MeUpdate, UserCreate, UserUpdate
from app.features.users.service import (
    avatar_response,
    remove_avatar,
    remove_files,
    save_avatar,
)
from app.shared.database import get_session, save
from app.shared.security import hash_secret
from app.shared.storage import read_upload

me_router = APIRouter(prefix="/api/me", tags=["me"])


@me_router.get("", response_model=UserRead)
def get_me(user: User = Depends(current_user)):
    return user


@me_router.patch("", response_model=UserRead)
def update_me(payload: MeUpdate, user: User = Depends(current_user), session: Session = Depends(get_session)):
    changes = payload.model_dump(exclude_unset=True, exclude_none=True)
    if changes.pop("reset_overview", False):
        changes["overview_layout"] = None
    for field in ("username", "email"):
        if field in changes:
            changes[field] = changes[field].lower()
    security.ensure_unique(session, changes.get("username"), changes.get("email"), exclude_id=user.id)
    for field, value in changes.items():
        setattr(user, field, value)
    return save(session, user)


@me_router.put("/avatar", response_model=UserRead)
async def upload_avatar(file: UploadFile = File(...), user: User = Depends(current_user),
                        session: Session = Depends(get_session)):
    save_avatar(user, await read_upload(file))
    return save(session, user)


@me_router.delete("/avatar", response_model=UserRead)
def delete_avatar(user: User = Depends(current_user), session: Session = Depends(get_session)):
    remove_avatar(user)
    return save(session, user)


@me_router.get("/avatar")
def get_avatar(user: User = Depends(current_user)):
    return avatar_response(user, user)


router = APIRouter(prefix="/api/users", tags=["users"])


def _get(session: Session, user_id: int) -> User:
    user = auth_repository.get(session, user_id)
    if user is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, t("user_not_found"))
    return user


@router.get("", response_model=list[UserRead], dependencies=[Depends(admin_user)])
def list_users(session: Session = Depends(get_session)):
    return auth_repository.list_all(session)


@router.get("/{user_id}", response_model=UserRead, dependencies=[Depends(admin_user)])
def get_user(user_id: int, session: Session = Depends(get_session)):
    return _get(session, user_id)


@router.post("", response_model=UserWithKey, status_code=status.HTTP_201_CREATED,
             dependencies=[Depends(admin_user)])
def create_user(payload: UserCreate, response: Response, session: Session = Depends(get_session)):
    """The recovery key is returned only once; the admin hands it to the new user."""
    username, email = payload.username.lower(), payload.email.lower()
    security.ensure_unique(session, username, email)
    security.check_password(payload.password, settings_service.load(session))
    user = User(username=username, email=email, role=payload.role, language=payload.language,
                password_hash=hash_secret(payload.password), recovery_key_hash="")
    key = security.rotate_recovery_key(user)
    save(session, user)
    response.headers["Location"] = f"/api/users/{user.id}"
    return UserWithKey(user=UserRead.model_validate(user), recovery_key=key)


@router.patch("/{user_id}", response_model=UserRead, dependencies=[Depends(admin_user)])
def update_user(user_id: int, payload: UserUpdate, session: Session = Depends(get_session)):
    user = _get(session, user_id)
    changes = payload.model_dump(exclude_unset=True, exclude_none=True)
    for field in ("username", "email"):
        if field in changes:
            changes[field] = changes[field].lower()
    security.ensure_unique(session, changes.get("username"), changes.get("email"), exclude_id=user.id)
    if changes.get("role") == UserRole.USER and user.role == UserRole.ADMIN and auth_repository.admin_count(session) <= 1:
        raise HTTPException(status.HTTP_409_CONFLICT, t("last_admin"))
    if password := changes.pop("password", None):
        security.check_password(password, settings_service.load(session))
        user.password_hash = hash_secret(password)
        user.session_version += 1
        security.register_success(user)  # also unlocks the account
    for field, value in changes.items():
        setattr(user, field, value)
    return save(session, user)


@router.delete("/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_user(user_id: int, admin: User = Depends(admin_user), session: Session = Depends(get_session)):
    """Delete the user along with applications, events, profile and files."""
    user = _get(session, user_id)
    if user.id == admin.id:
        raise HTTPException(status.HTTP_409_CONFLICT, t("cannot_delete_self"))
    auth_repository.delete(session, user)
    session.commit()
    remove_files(user_id)


@router.get("/{user_id}/avatar")
def get_avatar(user_id: int, viewer: User = Depends(current_user), session: Session = Depends(get_session)):  # noqa: F811  OpenAPI operation id
    return avatar_response(auth_repository.get(session, user_id), viewer)
