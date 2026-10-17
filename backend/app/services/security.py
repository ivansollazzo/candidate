"""Passwords, recovery keys and sessions.

Passwords and recovery keys are stored as Argon2 hashes (pwdlib); the session is a signed JWT (PyJWT)
in an HttpOnly cookie, invalidated when the password changes.
"""

import re
import secrets
from datetime import datetime, timedelta, timezone

import jwt
from fastapi import Depends, HTTPException, Request, Response, status
from pwdlib import PasswordHash
from sqlmodel import Session

from app.db import get_session
from app.i18n import t
from app.models import AppSettings, User, UserRole
from app.services import app_settings

COOKIE_NAME = "candidate_session"
ALGORITHM = "HS256"
# Alphabet without ambiguous characters (0/O, 1/I/L)
KEY_ALPHABET = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"
KEY_GROUPS, KEY_GROUP_SIZE = 6, 4

password_hash = PasswordHash.recommended()
# Used when the username doesn't exist, so response time stays the same
_DUMMY_HASH = password_hash.hash(secrets.token_hex(16))


def hash_secret(value: str) -> str:
    return password_hash.hash(value)


def verify_secret(value: str, hashed: str | None) -> bool:
    return password_hash.verify(value, hashed or _DUMMY_HASH) and hashed is not None


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


def new_recovery_key() -> str:
    """Key like "ABCD-EFGH-…": 24 random characters, about 119 bits."""
    chars = "".join(secrets.choice(KEY_ALPHABET) for _ in range(KEY_GROUPS * KEY_GROUP_SIZE))
    return "-".join(chars[i:i + KEY_GROUP_SIZE] for i in range(0, len(chars), KEY_GROUP_SIZE))


def normalize_recovery_key(value: str) -> str:
    chars = re.sub(r"[^A-Z0-9]", "", value.upper())
    return "-".join(chars[i:i + KEY_GROUP_SIZE] for i in range(0, len(chars), KEY_GROUP_SIZE))


def rotate_recovery_key(user: User) -> str:
    key = new_recovery_key()
    user.recovery_key_hash = hash_secret(key)
    return key


# Lockout after failed attempts

def _now() -> datetime:
    return datetime.now(timezone.utc)


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

def start_session(response: Response, user: User, settings: AppSettings) -> None:
    expires = _now() + timedelta(hours=settings.session_hours)
    token = jwt.encode({"sub": str(user.id), "sv": user.session_version, "exp": expires},
                       settings.secret_key, algorithm=ALGORITHM)
    # HttpOnly: page JavaScript can't read it; SameSite=Strict: no cross-site requests.
    # Not "Secure" because the app runs over http on localhost.
    response.set_cookie(COOKIE_NAME, token, max_age=settings.session_hours * 3600, httponly=True, samesite="strict",
                        path="/api")


def end_session(response: Response) -> None:
    response.delete_cookie(COOKIE_NAME, path="/api")


def current_user(request: Request, session: Session = Depends(get_session)) -> User:
    token = request.cookies.get(COOKIE_NAME)
    if not token:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, t("not_authenticated"))
    try:
        payload = jwt.decode(token, app_settings.load(session).secret_key, algorithms=[ALGORITHM])
        user = session.get(User, int(payload["sub"]))
    except (jwt.PyJWTError, KeyError, ValueError):
        user = None
    if user is None or user.session_version != payload.get("sv"):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, t("not_authenticated"))
    return user


def admin_user(user: User = Depends(current_user)) -> User:
    if user.role != UserRole.ADMIN:
        raise HTTPException(status.HTTP_403_FORBIDDEN, t("admin_required"))
    return user
