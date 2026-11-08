"""Whether the app is in maintenance: a backup being restored, or an update being installed.

The middleware answering 503, the job worker and the update and backup endpoints all read it here.
The updater service shares the folder updates_dir with the backend (see updater/updater.sh).
"""

import json
import threading
from pathlib import Path

from app.core.config import get_settings

_restoring = threading.Event()
_restore_lock = threading.Lock()


def restoring() -> bool:
    return _restoring.is_set()


def restore_started() -> bool:
    """Mark a restore as running; False if one already is."""
    with _restore_lock:
        if _restoring.is_set():
            return False
        _restoring.set()
        return True


def restore_finished() -> None:
    _restoring.clear()


def updater_file(name: str) -> Path:
    return get_settings().updates_dir / name


def _read(name: str) -> dict | None:
    try:
        return json.loads(updater_file(name).read_text())
    except (OSError, ValueError):
        return None


def read_state() -> dict | None:
    """State written by the updater; None when it is not running (e.g. backend outside Docker)."""
    return _read("state.json")


def pending_action() -> str | None:
    """Request written but not yet picked up by the updater (it looks every few seconds)."""
    return (_read("request.json") or {}).get("action")


def installing() -> bool:
    """An install is requested or running: no AI job starts meanwhile."""
    return (read_state() or {}).get("status") == "updating" or pending_action() == "install"
