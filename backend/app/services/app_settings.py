"""App settings stored in the database and shared with the llm service."""

import json
import logging
import secrets

from fastapi import HTTPException, status
from sqlmodel import Session

from app.config import get_settings
from app.i18n import t
from app.models import AppSettings

log = logging.getLogger(__name__)

SETTINGS_ID = 1


def load(session: Session) -> AppSettings:
    settings = session.get(AppSettings, SETTINGS_ID)
    if settings is None or settings.secret_key is None:
        settings = settings or AppSettings(id=SETTINGS_ID)
        # Session signing key lives in the database; changing it logs everyone out
        settings.secret_key = secrets.token_urlsafe(64)
        session.add(settings)
        session.commit()
        session.refresh(settings)
    return settings


def require_llm(session: Session) -> None:
    if not load(session).llm_enabled:
        raise HTTPException(status.HTTP_409_CONFLICT, t("ai_disabled"))


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
        log.exception("Impossibile scrivere %s", target)
