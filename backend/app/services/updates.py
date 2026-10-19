"""Updates through the updater service, which shares the folder updates_dir with the backend (see updater/updater.sh)."""

import json
import logging

from fastapi import HTTPException, status

from app import __build__, __version__
from app.config import get_settings
from app.i18n import t

log = logging.getLogger(__name__)


def release_key(version: str, build: str) -> tuple:
    """Sortable key: version parts as numbers, then the build (yyyymmdd.hhmm)."""
    parts = tuple(int(part) if part.isdigit() else 0 for part in version.split("."))
    try:
        return parts, float(build)
    except ValueError:
        return parts, 0.0


INSTALLED = release_key(__version__, __build__)


def is_newer(version: str, build: str) -> bool:
    return bool(version) and release_key(version, build) > INSTALLED


def read_state() -> dict | None:
    """State written by the updater; None when it is not running (e.g. backend outside Docker)."""
    try:
        return json.loads((get_settings().updates_dir / "state.json").read_text())
    except (OSError, ValueError):
        return None


def pending_action() -> str | None:
    """Request written but not yet picked up by the updater (it looks every few seconds)."""
    try:
        return json.loads((get_settings().updates_dir / "request.json").read_text()).get("action")
    except (OSError, ValueError):
        return None


def overview() -> dict:
    state = read_state() or {"status": "unavailable"}
    if state.get("status") == "idle" and (action := pending_action()):
        state = {**state, "status": "updating" if action == "install" else "checking", "step": "fetch"}
    branches = [{**branch, "newer": is_newer(branch.get("version", ""), branch.get("build", ""))}
                for branch in state.get("branches", [])]
    current = next((branch for branch in branches if branch["name"] == state.get("branch")), None)
    return {
        "status": state.get("status", "unavailable"),
        "step": state.get("step") or None,
        "branch": state.get("branch") or None,
        "commit": state.get("commit") or None,
        "checked_at": state.get("checked_at") or None,
        "version": __version__,
        "build": __build__,
        "branches": branches,
        "update_available": bool(current and current["newer"]),
        "last": state.get("last"),
    }


def request(action: str, **fields) -> None:
    state = read_state()
    if state is None or state.get("status") == "unavailable":
        raise HTTPException(status.HTTP_409_CONFLICT, t("updates_unavailable"))
    if state.get("status") != "idle" or pending_action():
        raise HTTPException(status.HTTP_409_CONFLICT, t("update_busy"))
    if action == "install":
        branch = next((b for b in state.get("branches", []) if b.get("name") == fields["branch"]), None)
        if branch is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, t("branch_not_found"))
        # Only a newer release can be installed: the database is never taken back to an older schema
        if not is_newer(branch.get("version", ""), branch.get("build", "")):
            raise HTTPException(status.HTTP_409_CONFLICT, t("update_not_newer"))
    target = get_settings().updates_dir / "request.json"
    tmp = target.with_suffix(".tmp")
    tmp.write_text(json.dumps({"action": action, **fields}))
    tmp.replace(target)
