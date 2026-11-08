"""Updates through the updater service, which shares the folder updates_dir with the backend (see updater/updater.sh).

The updater lists the branches of the repository with the release of their latest commit and whether its images
are published. The admin follows a branch, "stable" until they pick another.
"""

import json

from fastapi import HTTPException, status

from app import __build__, __version__
from app.core.i18n import t
from app.shared.maintenance import pending_action, read_state, updater_file

DEFAULT_BRANCH = "stable"


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


def branches(state: dict) -> list[dict]:
    """Branches of the repository, each with whether its release is newer than the installed one."""
    return [{**branch, "published": bool(branch.get("published")),
             "newer": is_newer(branch.get("version", ""), branch.get("build", ""))}
            for branch in state.get("branches", [])]


def overview(selected: str | None) -> dict:
    """Updater state; an update is available when the selected branch has a newer release whose images are
    published."""
    state = read_state() or {"status": "unavailable"}
    if state.get("status") == "idle" and (action := pending_action()) in ("install", "check"):
        state = {**state, "status": "updating" if action == "install" else "checking", "step": "backup", "progress": 0}
    listed = branches(state)
    selected = selected or DEFAULT_BRANCH
    target = next((branch for branch in listed if branch["name"] == selected), None)
    return {
        "status": state.get("status", "unavailable"),
        "step": state.get("step") or None,
        "progress": state.get("progress") or 0,
        "selected_branch": selected,
        "checked_at": state.get("checked_at") or None,
        "version": __version__,
        "build": __build__,
        "branches": listed,
        "update_available": bool(target and target["newer"] and target["published"]),
        "last": state.get("last"),
        "check_error": state.get("check_error"),
    }


def request(action: str, selected: str | None = None) -> None:
    """Ask the updater to check, or to install the release of the selected branch."""
    state = read_state()
    if state is None or state.get("status") == "unavailable":
        raise HTTPException(status.HTTP_409_CONFLICT, t("updates_unavailable"))
    if state.get("status") != "idle" or pending_action():
        raise HTTPException(status.HTTP_409_CONFLICT, t("update_busy"))
    fields = {}
    if action == "install":
        name = selected or DEFAULT_BRANCH
        branch = next((branch for branch in branches(state) if branch["name"] == name), None)
        if branch is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, t("branch_not_found"))
        # Only a newer release can be installed: the database is never taken back to an older schema
        if not branch["newer"]:
            raise HTTPException(status.HTTP_409_CONFLICT, t("update_not_newer"))
        if not branch["published"]:
            raise HTTPException(status.HTTP_409_CONFLICT, t("update_not_published"))
        fields["branch"] = name
    tmp = updater_file("request.tmp")
    tmp.write_text(json.dumps({"action": action, **fields}))
    tmp.replace(updater_file("request.json"))
