"""First-run setup (admin creation), the session (sign in, sign out), password resets via recovery key, and the
current user's password and recovery key."""

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlmodel import Session

from app.core.i18n import t
from app.features.auth import rate_limit
from app.features.auth import service as security
from app.features.auth.dependencies import current_user
from app.features.auth.models import User, UserRole
from app.features.auth.schemas import (
    AuthStatus,
    LoginRequest,
    PasswordChange,
    PasswordConfirm,
    PasswordPolicy,
    ResetRequest,
    SetupRequest,
    UserRead,
    UserWithKey,
)
from app.features.settings import service as settings_service
from app.shared.database import get_session, save
from app.shared.security import hash_secret, normalize_recovery_key, verify_secret

router = APIRouter(prefix="/api", tags=["auth"])


@router.get("/setup", response_model=AuthStatus)
def auth_status(session: Session = Depends(get_session)):
    """Public: whether the admin still needs to be created, plus the password rules."""
    settings = settings_service.load(session)
    return AuthStatus(setup_required=not security.users_exist(session), password_policy=PasswordPolicy.model_validate(settings))


@router.post("/setup", response_model=UserWithKey, status_code=status.HTTP_201_CREATED)
def setup(payload: SetupRequest, response: Response, session: Session = Depends(get_session)):
    """Create the first user as admin. Only allowed while no users exist."""
    if security.users_exist(session):
        raise HTTPException(status.HTTP_409_CONFLICT, t("setup_done"))
    settings = settings_service.load(session)
    security.check_password(payload.password, settings)
    user = User(username=payload.username.lower(), email=payload.email.lower(), role=UserRole.ADMIN,
                language=payload.language, password_hash=hash_secret(payload.password), recovery_key_hash="")
    key = security.rotate_recovery_key(user)
    save(session, user)
    security.start_session(response, user, settings)
    # The new admin is the user of this session
    response.headers["Location"] = "/api/me"
    return UserWithKey(user=UserRead.model_validate(user), recovery_key=key)


@router.post("/session", response_model=UserRead)
def login(payload: LoginRequest, request: Request, response: Response, session: Session = Depends(get_session)):
    settings = settings_service.load(session)
    rate_limit.ensure_allowed(request, settings)
    user = security.find_user(session, payload.username)
    if user is not None:
        security.ensure_not_locked(user)
    if not verify_secret(payload.password, user.password_hash if user else None):
        if user is not None:
            security.register_failure(user, settings)
            save(session, user)
        rate_limit.register_failure(request, settings)
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, t("invalid_credentials"))
    security.register_success(user)
    save(session, user)
    security.start_session(response, user, settings)
    return user


@router.delete("/session", status_code=status.HTTP_204_NO_CONTENT)
def logout(response: Response):
    security.end_session(response)


@router.post("/password-resets", response_model=UserWithKey)
def reset_password(payload: ResetRequest, request: Request, response: Response,
                   session: Session = Depends(get_session)):
    """Set a new password via recovery key; the used key is replaced with a new one."""
    settings = settings_service.load(session)
    rate_limit.ensure_allowed(request, settings)
    user = security.find_user(session, payload.username)
    if user is not None:
        security.ensure_not_locked(user)
    key = normalize_recovery_key(payload.recovery_key)
    if not verify_secret(key, user.recovery_key_hash if user else None):
        if user is not None:
            security.register_failure(user, settings)
            save(session, user)
        rate_limit.register_failure(request, settings)
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, t("invalid_recovery_key"))
    security.check_password(payload.new_password, settings)
    user.password_hash = hash_secret(payload.new_password)
    user.session_version += 1
    new_key = security.rotate_recovery_key(user)
    security.register_success(user)
    save(session, user)
    security.start_session(response, user, settings)
    return UserWithKey(user=UserRead.model_validate(user), recovery_key=new_key)

me_router = APIRouter(prefix="/api/me", tags=["me"])


def _confirm_password(user: User, password: str) -> None:
    if not verify_secret(password, user.password_hash):
        raise HTTPException(status.HTTP_403_FORBIDDEN, t("wrong_password"))


@me_router.put("/password", response_model=UserRead)
def change_password(payload: PasswordChange, response: Response, user: User = Depends(current_user),
                    session: Session = Depends(get_session)):
    _confirm_password(user, payload.current_password)
    settings = settings_service.load(session)
    security.check_password(payload.new_password, settings)
    user.password_hash = hash_secret(payload.new_password)
    # Other open sessions are invalidated; this one continues with a new cookie
    user.session_version += 1
    save(session, user)
    security.start_session(response, user, settings)
    return user


@me_router.post("/recovery-key")
def new_recovery_key(payload: PasswordConfirm, user: User = Depends(current_user),
                     session: Session = Depends(get_session)):
    """Generate a new downloadable recovery key; the old one stops working."""
    _confirm_password(user, payload.password)
    key = security.rotate_recovery_key(user)
    save(session, user)
    return {"recovery_key": key}
