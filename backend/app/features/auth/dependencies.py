"""FastAPI dependencies giving the signed-in user; every router uses them."""

from fastapi import Depends, HTTPException, Request, Response, status
from sqlmodel import Session

from app.core.i18n import t
from app.features.auth import repository, service
from app.features.auth.models import User, UserRole
from app.features.settings import service as settings_service
from app.shared.database import get_session
from app.shared.security import read_token


def _unauthorized() -> HTTPException:
    return HTTPException(status.HTTP_401_UNAUTHORIZED, t("not_authenticated"))


def current_user(request: Request, response: Response, session: Session = Depends(get_session)) -> User:
    token = request.cookies.get(service.cookie_names()[0])
    if not token:
        raise _unauthorized()
    settings = settings_service.load(session)
    payload = read_token(token, settings.secret_key)
    try:
        user = repository.get(session, int(payload["sub"])) if payload else None
    except (KeyError, ValueError):
        user = None
    if user is None or user.session_version != payload.get("sv") or payload.get("scheme") != service.scheme():
        raise _unauthorized()
    # Sliding session: using the app pushes the expiry forward, so it only ends after
    # session_hours of inactivity (renewed at most every service.RENEW_MINUTES)
    left = payload["exp"] - service.now().timestamp()
    if left < settings.session_hours * 3600 - service.RENEW_MINUTES * 60:
        service.start_session(response, user, settings)
    return user


def admin_user(user: User = Depends(current_user)) -> User:
    if user.role != UserRole.ADMIN:
        raise HTTPException(status.HTTP_403_FORBIDDEN, t("admin_required"))
    return user
