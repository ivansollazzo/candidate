"""App settings stored in the database and shared with the llm service and the updater."""

import json
import logging
import secrets
from collections.abc import Callable

from fastapi import HTTPException, status
from sqlmodel import Session

from app.core.config import get_settings
from app.core.i18n import t
from app.features.settings import repository
from app.features.settings.models import AppSettings

log = logging.getLogger(__name__)

# Run in the same transaction when the admin turns the AI features off (registered in main.wire)
_ai_disabled: list[Callable[[Session], None]] = []


def on_ai_disabled(callback: Callable[[Session], None]) -> None:
    _ai_disabled.append(callback)


def ensure(session: Session) -> AppSettings:
    """At startup: the settings row and the session signing key exist. Committed."""
    settings = repository.get(session) or AppSettings(id=repository.SETTINGS_ID)
    if settings.secret_key is None:
        # Session signing key lives in the database; changing it logs everyone out
        settings.secret_key = secrets.token_urlsafe(64)
        repository.add(session, settings)
        session.commit()
        session.refresh(settings)
    return settings


def load(session: Session) -> AppSettings:
    settings = repository.get(session)
    if settings is None:
        raise RuntimeError("Settings missing: they are created at startup (settings.service.ensure)")
    return settings


def require_llm(session: Session) -> None:
    if not load(session).llm_enabled:
        raise HTTPException(status.HTTP_409_CONFLICT, t("ai_disabled"))


def apply_changes(session: Session, settings: AppSettings, changes: dict) -> None:
    """Set the given fields; turning the AI off runs the registered callbacks. Not committed."""
    if settings.llm_enabled and changes.get("llm_enabled") is False:
        for callback in _ai_disabled:
            callback(session)
    for field, value in changes.items():
        setattr(settings, field, value)
    settings.update_branch = settings.update_branch or None
    repository.add(session, settings)


def publish(settings: AppSettings) -> None:
    """Write choices to the shared volumes: the llm service starts, stops or restarts Ollama accordingly,
    the updater follows the check interval."""
    _write(get_settings().llm_runtime_file.parent / "settings.json",
           {"llm_enabled": settings.llm_enabled, "llm_accelerator": settings.llm_accelerator})
    _write(get_settings().updates_dir / "settings.json", {"check_hours": settings.update_check_hours})


def _write(target, data: dict) -> None:
    if not target.parent.is_dir():
        return  # backend running outside Docker
    try:
        tmp = target.with_suffix(".tmp")
        tmp.write_text(json.dumps(data))
        tmp.replace(target)
    except OSError:
        log.exception("Unable to write %s", target)
