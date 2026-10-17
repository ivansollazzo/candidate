"""User management, admin only: only the admin can create users."""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlmodel import Session, select

from app.api.me import avatar_response
from app.db import get_session, save
from app.i18n import t
from app.models import User, UserRole
from app.schemas import UserCreate, UserRead, UserUpdate, UserWithKey
from app.services import app_settings, security
from app.services.users import admin_count, ensure_unique, remove_files

router = APIRouter(prefix="/api/users", tags=["users"])


def _get(session: Session, user_id: int) -> User:
    user = session.get(User, user_id)
    if user is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, t("user_not_found"))
    return user


@router.get("", response_model=list[UserRead], dependencies=[Depends(security.admin_user)])
def list_users(session: Session = Depends(get_session)):
    return session.exec(select(User).order_by(User.username)).all()


@router.post("", response_model=UserWithKey, status_code=status.HTTP_201_CREATED,
             dependencies=[Depends(security.admin_user)])
def create_user(payload: UserCreate, session: Session = Depends(get_session)):
    """The recovery key is returned only once; the admin hands it to the new user."""
    username, email = payload.username.lower(), payload.email.lower()
    ensure_unique(session, username, email)
    security.check_password(payload.password, app_settings.load(session))
    user = User(username=username, email=email, role=payload.role, language=payload.language,
                password_hash=security.hash_secret(payload.password), recovery_key_hash="")
    key = security.rotate_recovery_key(user)
    session.add(user)
    session.commit()
    session.refresh(user)
    return UserWithKey(user=UserRead.model_validate(user), recovery_key=key)


@router.patch("/{user_id}", response_model=UserRead)
def update_user(user_id: int, payload: UserUpdate, admin: User = Depends(security.admin_user),
                session: Session = Depends(get_session)):
    user = _get(session, user_id)
    changes = payload.model_dump(exclude_unset=True, exclude_none=True)
    for field in ("username", "email"):
        if field in changes:
            changes[field] = changes[field].lower()
    ensure_unique(session, changes.get("username"), changes.get("email"), exclude_id=user.id)
    if changes.get("role") == UserRole.USER and user.role == UserRole.ADMIN and admin_count(session) <= 1:
        raise HTTPException(status.HTTP_409_CONFLICT, t("last_admin"))
    if password := changes.pop("password", None):
        security.check_password(password, app_settings.load(session))
        user.password_hash = security.hash_secret(password)
        user.session_version += 1
        security.register_success(user)  # also unlocks the account
    for field, value in changes.items():
        setattr(user, field, value)
    return save(session, user)


@router.delete("/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_user(user_id: int, admin: User = Depends(security.admin_user), session: Session = Depends(get_session)):
    """Delete the user along with applications, events, profile and files."""
    user = _get(session, user_id)
    if user.id == admin.id:
        raise HTTPException(status.HTTP_409_CONFLICT, t("cannot_delete_self"))
    session.delete(user)
    session.commit()
    remove_files(user_id)


@router.get("/{user_id}/avatar")
def get_avatar(user_id: int, viewer: User = Depends(security.current_user), session: Session = Depends(get_session)):
    return avatar_response(session.get(User, user_id), viewer)
