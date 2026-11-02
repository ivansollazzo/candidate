"""Updates through the updater service, which shares the folder updates_dir with the backend (see updater/updater.sh).

The updater lists the branches and release tags of the repository with their release and whether the images of
their commit are published. The admin follows a channel or a branch: "@stable" is the newest release tag without
"-" (v2.1), "@beta" the newest of all tags (v2.1-beta.1 included), a branch its latest commit.
"""

import json

from fastapi import HTTPException, status

from app import __build__, __version__
from app.config import get_settings
from app.i18n import t

STABLE, BETA = "@stable", "@beta"
CHANNELS = (STABLE, BETA)


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


def _file(name: str):
    return get_settings().updates_dir / name


def _read(name: str) -> dict | None:
    try:
        return json.loads(_file(name).read_text())
    except (OSError, ValueError):
        return None


def read_state() -> dict | None:
    """State written by the updater; None when it is not running (e.g. backend outside Docker)."""
    return _read("state.json")


def pending_action() -> str | None:
    """Request written but not yet picked up by the updater (it looks every few seconds)."""
    return (_read("request.json") or {}).get("action")


def installing() -> bool:
    """An install is requested or running: no AI job starts meanwhile (see services/jobs.py)."""
    return (read_state() or {}).get("status") == "updating" or pending_action() == "install"


def _channel(tags: list[dict], name: str) -> dict | None:
    """The newest published tag of a channel, as a source named after the channel."""
    candidates = [tag for tag in tags if tag.get("published") and (name == BETA or "-" not in tag.get("name", ""))]
    if not candidates:
        return None
    newest = max(candidates, key=lambda tag: release_key(tag.get("version", ""), tag.get("build", "")))
    return {**newest, "name": name, "kind": "channel", "tag": newest.get("name")}


def sources(state: dict) -> list[dict]:
    """Channels first, then branches, each with whether it is newer than the installed release."""
    listed = state.get("sources", [])
    tags = [source for source in listed if source.get("kind") == "tag"]
    branches = [source for source in listed if source.get("kind") == "branch"]
    channels = [channel for name in CHANNELS if (channel := _channel(tags, name))]
    return [{**source, "published": bool(source.get("published")),
             "newer": is_newer(source.get("version", ""), source.get("build", ""))}
            for source in channels + branches]


def overview(selected: str | None) -> dict:
    """Updater state; an update is available when the selected source has a newer release whose images are
    published. Until the admin picks one, the stable channel is followed."""
    state = read_state() or {"status": "unavailable"}
    if state.get("status") == "idle" and (action := pending_action()) in ("install", "check"):
        state = {**state, "status": "updating" if action == "install" else "checking", "step": "backup", "progress": 0}
    listed = sources(state)
    selected = selected or STABLE
    target = next((source for source in listed if source["name"] == selected), None)
    return {
        "status": state.get("status", "unavailable"),
        "step": state.get("step") or None,
        "progress": state.get("progress") or 0,
        "selected_source": selected,
        "checked_at": state.get("checked_at") or None,
        "version": __version__,
        "build": __build__,
        "sources": listed,
        "update_available": bool(target and target["newer"] and target["published"]),
        "last": state.get("last"),
        "check_error": state.get("check_error"),
    }


def request(action: str, selected: str | None = None) -> None:
    """Ask the updater to check, or to install the release of the selected source."""
    state = read_state()
    if state is None or state.get("status") == "unavailable":
        raise HTTPException(status.HTTP_409_CONFLICT, t("updates_unavailable"))
    if state.get("status") != "idle" or pending_action():
        raise HTTPException(status.HTTP_409_CONFLICT, t("update_busy"))
    fields = {}
    if action == "install":
        name = selected or STABLE
        source = next((source for source in sources(state) if source["name"] == name), None)
        if source is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, t("source_not_found"))
        # Only a newer release can be installed: the database is never taken back to an older schema
        if not source["newer"]:
            raise HTTPException(status.HTTP_409_CONFLICT, t("update_not_newer"))
        if not source["published"]:
            raise HTTPException(status.HTTP_409_CONFLICT, t("update_not_published"))
        fields["ref"] = source["ref"]
    tmp = _file("request.tmp")
    tmp.write_text(json.dumps({"action": action, **fields}))
    tmp.replace(_file("request.json"))
