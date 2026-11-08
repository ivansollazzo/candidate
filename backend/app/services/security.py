"""Password policy, lockout and sessions.

The session is a signed token in an HttpOnly cookie, invalidated when the password changes; hashes, recovery
keys and token signing are in app.shared.security.
"""

import re
import secrets
from contextvars import ContextVar
from datetime import UTC, datetime, timedelta

from fastapi import Depends, HTTPException, Request, Response, status
from sqlmodel import Session

from app.core.i18n import t
from app.models import AppSettings, User, UserRole
from app.services import app_settings
from app.shared.database import get_session
from app.shared.security import hash_secret, new_recovery_key, read_token, sign_token

# One cookie per protocol. A browser keeps a cookie set over HTTPS with the Secure flag and doesn't let plain
# HTTP replace it: with the same name, after turning HTTPS off the new session cookie would be thrown away and
# every sign-in would end at once. The __Secure- prefix makes browsers accept that one only over HTTPS.
COOKIE_NAME = "candidate_session"
SECURE_COOKIE_NAME = "__Secure-candidate_session"
# A session in use is renewed when its token is older than this
RENEW_MINUTES = 10

# The request came over HTTPS (X-Forwarded-Proto set by Caddy), set by a middleware in main.py
secure_request: ContextVar[bool] = ContextVar("secure_request", default=False)

def password_problems(password: str, settings: AppSettings) -> list[str]:
    problems = []
    if len(password) < settings.password_min_length:
        problems.append(t("password_rule_length", count=settings.password_min_length))
    if settings.password_require_uppercase and not re.search(r"[A-Z]", password):
        problems.append(t("password_rule_uppercase"))
    if settings.password_require_digit and not re.search(r"\d", password):
        problems.append(t("password_rule_digit"))
    if settings.password_require_symbol and not re.search(r"[^A-Za-z0-9]", password):
        problems.append(t("password_rule_symbol"))
    return problems


def check_password(password: str, settings: AppSettings) -> None:
    if problems := password_problems(password, settings):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, t("password_invalid", rules=", ".join(problems)))


def rotate_recovery_key(user: User) -> str:
    key = new_recovery_key()
    user.recovery_key_hash = hash_secret(key)
    return key


# Lockout after failed attempts

def _now() -> datetime:
    return datetime.now(UTC)


def ensure_not_locked(user: User) -> None:
    if user.locked_until and user.locked_until > _now():
        minutes = max(1, round((user.locked_until - _now()).total_seconds() / 60))
        raise HTTPException(status.HTTP_423_LOCKED, t("account_locked", minutes=minutes))


def register_failure(user: User, settings: AppSettings) -> None:
    user.failed_logins += 1
    if settings.max_login_attempts and user.failed_logins >= settings.max_login_attempts:
        user.locked_until = _now() + timedelta(minutes=settings.lockout_minutes)
        user.failed_logins = 0


def register_success(user: User) -> None:
    user.failed_logins = 0
    user.locked_until = None


# Session

def _scheme() -> str:
    return "https" if secure_request.get() else "http"


def _cookie_names() -> tuple[str, str]:
    """Cookie of this request's protocol, and the one of the other protocol."""
    return (SECURE_COOKIE_NAME, COOKIE_NAME) if secure_request.get() else (COOKIE_NAME, SECURE_COOKIE_NAME)


def start_session(response: Response, user: User, settings: AppSettings) -> None:
    expires = _now() + timedelta(hours=settings.session_hours)
    # The protocol is part of the token: a session opened over HTTP isn't valid over HTTPS and vice versa
    token = sign_token({"sub": str(user.id), "sv": user.session_version, "exp": expires, "scheme": _scheme()},
                       settings.secret_key)
    name, other = _cookie_names()
    # HttpOnly: page JavaScript can't read it; SameSite=Strict: no cross-site requests; Secure (sent only
    # over HTTPS) when the app is served over HTTPS (Settings › Security › HTTPS)
    response.set_cookie(name, token, max_age=settings.session_hours * 3600, httponly=True, samesite="strict",
                        path="/api", secure=secure_request.get())
    # A leftover of the other protocol is removed where the browser allows it
    response.delete_cookie(other, path="/api", secure=other == SECURE_COOKIE_NAME)


def end_session(response: Response) -> None:
    response.delete_cookie(COOKIE_NAME, path="/api")
    response.delete_cookie(SECURE_COOKIE_NAME, path="/api", secure=True)


def end_all_sessions(settings: AppSettings) -> None:
    """Every session of every user ends (e.g. when HTTPS is turned on or off): a new signing key. Not committed."""
    settings.secret_key = secrets.token_urlsafe(64)


def _unauthorized() -> HTTPException:
    return HTTPException(status.HTTP_401_UNAUTHORIZED, t("not_authenticated"))


def current_user(request: Request, response: Response, session: Session = Depends(get_session)) -> User:
    token = request.cookies.get(_cookie_names()[0])
    if not token:
        raise _unauthorized()
    settings = app_settings.load(session)
    payload = read_token(token, settings.secret_key)
    try:
        user = session.get(User, int(payload["sub"])) if payload else None
    except (KeyError, ValueError):
        user = None
    if user is None or user.session_version != payload.get("sv") or payload.get("scheme", "http") != _scheme():
        raise _unauthorized()
    # Sliding session: using the app pushes the expiry forward, so it only ends after
    # session_hours of inactivity (renewed at most every RENEW_MINUTES)
    left = payload["exp"] - _now().timestamp()
    if left < settings.session_hours * 3600 - RENEW_MINUTES * 60:
        start_session(response, user, settings)
    return user


def admin_user(user: User = Depends(current_user)) -> User:
    if user.role != UserRole.ADMIN:
        raise HTTPException(status.HTTP_403_FORBIDDEN, t("admin_required"))
    return user
