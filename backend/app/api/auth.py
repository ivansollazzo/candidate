"""First-run setup (admin creation), login, logout and password reset via recovery key."""

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy import update
from sqlmodel import Session, func, select

from app.db import get_session
from app.i18n import t
from app.models import Application, Profile, User, UserRole
from app.schemas import AuthStatus, LoginRequest, PasswordPolicy, ResetRequest, SetupRequest, UserRead, UserWithKey
from app.services import app_settings, security

router = APIRouter(prefix="/api/auth", tags=["auth"])


def _users_exist(session: Session) -> bool:
    return session.exec(select(func.count()).select_from(User)).one() > 0


def _find(session: Session, username: str) -> User | None:
    return session.exec(select(User).where(User.username == username.strip().lower())).first()


@router.get("/status", response_model=AuthStatus)
def auth_status(session: Session = Depends(get_session)):
    """Public: whether the admin still needs to be created, plus the password rules."""
    settings = app_settings.load(session)
    return AuthStatus(setup_required=not _users_exist(session), password_policy=PasswordPolicy.model_validate(settings))


@router.post("/setup", response_model=UserWithKey, status_code=status.HTTP_201_CREATED)
def setup(payload: SetupRequest, response: Response, session: Session = Depends(get_session)):
    """Create the first user as admin. Only allowed while no users exist."""
    if _users_exist(session):
        raise HTTPException(status.HTTP_409_CONFLICT, t("setup_done"))
    settings = app_settings.load(session)
    security.check_password(payload.password, settings)
    user = User(username=payload.username.lower(), email=payload.email.lower(), role=UserRole.ADMIN,
                language=payload.language, password_hash=security.hash_secret(payload.password), recovery_key_hash="")
    key = security.rotate_recovery_key(user)
    session.add(user)
    session.flush()
    # Applications and profile created before users existed are assigned to the admin
    session.exec(update(Application).where(Application.user_id.is_(None)).values(user_id=user.id))
    session.exec(update(Profile).where(Profile.user_id.is_(None)).values(user_id=user.id))
    session.commit()
    session.refresh(user)
    security.start_session(response, user, settings)
    return UserWithKey(user=UserRead.model_validate(user), recovery_key=key)


@router.post("/login", response_model=UserRead)
def login(payload: LoginRequest, response: Response, session: Session = Depends(get_session)):
    settings = app_settings.load(session)
    user = _find(session, payload.username)
    if user is not None:
        security.ensure_not_locked(user)
    if not security.verify_secret(payload.password, user.password_hash if user else None):
        if user is not None:
            security.register_failure(user, settings)
            session.add(user)
            session.commit()
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, t("invalid_credentials"))
    security.register_success(user)
    session.add(user)
    session.commit()
    session.refresh(user)
    security.start_session(response, user, settings)
    return user


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(response: Response):
    security.end_session(response)


@router.post("/reset", response_model=UserWithKey)
def reset_password(payload: ResetRequest, response: Response, session: Session = Depends(get_session)):
    """Set a new password via recovery key; the used key is replaced with a new one."""
    settings = app_settings.load(session)
    user = _find(session, payload.username)
    if user is not None:
        security.ensure_not_locked(user)
    key = security.normalize_recovery_key(payload.recovery_key)
    if not security.verify_secret(key, user.recovery_key_hash if user else None):
        if user is not None:
            security.register_failure(user, settings)
            session.add(user)
            session.commit()
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, t("invalid_recovery_key"))
    security.check_password(payload.new_password, settings)
    user.password_hash = security.hash_secret(payload.new_password)
    user.session_version += 1
    new_key = security.rotate_recovery_key(user)
    security.register_success(user)
    session.add(user)
    session.commit()
    session.refresh(user)
    security.start_session(response, user, settings)
    return UserWithKey(user=UserRead.model_validate(user), recovery_key=new_key)
