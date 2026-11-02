"""Backups through the backup service (backup/backup.py), reached on the Compose network.

While a backup is restored the app is in maintenance: every request but /api/health answers 503, no AI job
starts, and once database and files are back the migrations bring the database to this version.
"""

import logging
import subprocess
import sys
import threading
from datetime import UTC, datetime
from pathlib import Path

import httpx
from alembic.config import Config
from alembic.script import ScriptDirectory
from fastapi import HTTPException, status
from sqlmodel import Session

from app.config import get_settings
from app.db import engine
from app.i18n import t

log = logging.getLogger(__name__)

BACKEND_DIR = Path(__file__).resolve().parents[2]
# A backup or a restore can take a while with many attachments
TIMEOUT = httpx.Timeout(10, read=3600)

_restoring = threading.Event()
_last_restore: dict | None = None


def restoring() -> bool:
    return _restoring.is_set()


def last_restore() -> dict | None:
    return _last_restore


def _url(path: str) -> str:
    return f"{get_settings().backup_url}/{path}"


def call(method: str, path: str, **kwargs) -> httpx.Response:
    """A request to the backup service; its errors become the API's."""
    try:
        response = httpx.request(method, _url(path), timeout=TIMEOUT, **kwargs)
    except httpx.HTTPError as exc:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, t("backup_unavailable")) from exc
    if response.status_code == 409:
        raise HTTPException(status.HTTP_409_CONFLICT, t("backup_busy"))
    if response.status_code == 404:
        raise HTTPException(status.HTTP_404_NOT_FOUND, t("backup_not_found"))
    if response.is_error:
        detail = response.json().get("detail", "") if response.headers.get("content-type") == "application/json" else ""
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, t("backup_failed", detail=detail))
    return response


def known_revisions() -> set[str]:
    """Database revisions this version knows: a backup of a newer one can't be restored."""
    script = ScriptDirectory.from_config(Config(str(BACKEND_DIR / "alembic.ini")))
    return {revision.revision for revision in script.walk_revisions()}


def check_restorable(backup: dict) -> None:
    if backup.get("broken") or backup.get("revision") not in known_revisions():
        raise HTTPException(status.HTTP_409_CONFLICT, t("backup_too_new"))


def _finish_restore(name: str) -> None:
    """Restore in the background, then migrate the database and pick the app up again."""
    global _last_restore
    from app.services import app_settings, jobs

    result = {"name": name, "result": "ok", "detail": ""}
    try:
        call("POST", f"backups/{name}/restore", json={"safety": True})
    except HTTPException as exc:
        result = {**result, "result": "failed", "detail": str(exc.detail)}
    # Connections were closed by the restore; the migrations bring an older backup to this version
    engine.dispose()
    migrate = subprocess.run([sys.executable, "-m", "alembic", "upgrade", "head"], cwd=BACKEND_DIR,
                             capture_output=True, text=True)
    if migrate.returncode != 0:
        result = {**result, "result": "failed", "detail": (result["detail"] + "\n" + migrate.stderr[-2000:]).strip()}
    try:
        with Session(engine) as session:
            jobs.recover(session)
            app_settings.publish(app_settings.load(session))
    except Exception:
        log.exception("Unable to resume after the restore")
    _last_restore = {**result, "finished_at": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")}
    _restoring.clear()
    log.info("restore of %s: %s", name, result["result"])


def start_restore(name: str) -> None:
    if not _restoring.is_set():
        _restoring.set()
        threading.Thread(target=_finish_restore, args=(name,), name="restore", daemon=True).start()
