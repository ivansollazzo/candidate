"""Maintenance commands, for when the app can't be used from the browser. Run inside the backend container:

    docker compose exec backend python -m app.cli <command>

(if the backend doesn't start, `docker compose run --rm backend python -m app.cli <command>` works too)

https-off        turns HTTPS off (Settings › Security › HTTPS), e.g. when the app can no longer be opened from any
                 of its addresses. The web server is back on plain HTTP within a few seconds; everyone signs in again.
backups          lists the backups (Settings › Backup), newest first.
restore <name>   puts database and files back as in that backup; the current state is saved first as a
                 "restore" backup, so the step can be undone. Restart the backend afterwards:
                 docker compose restart backend
"""

import subprocess
import sys

from fastapi import HTTPException
from sqlmodel import Session

from app.services import app_settings, backups, security
from app.shared.database import engine


def https_off() -> int:
    with Session(engine) as session:
        settings = app_settings.load(session)
        settings.https_mode = "off"
        security.end_all_sessions(settings)
        session.add(settings)
        session.commit()
    print("HTTPS turned off: the app answers over plain HTTP within a few seconds. Everyone signs in again.")
    return 0


def list_backups() -> int:
    items = backups.call("GET", "backups").json()
    if not items:
        print("No backups yet.")
    known = backups.known_revisions()
    for item in items:
        usable = "" if not item.get("broken") and item.get("revision") in known else "  (can't be restored here)"
        note = f"  {item['note']}" if item.get("note") else ""
        print(f"{item['name']}  {item.get('kind', '')}  {item.get('version', '')} {item.get('build', '')}{note}{usable}")
    return 0


def restore(name: str) -> int:
    backup = next((item for item in backups.call("GET", "backups").json() if item["name"] == name), None)
    if backup is None:
        print(f"No backup named {name}: see `python -m app.cli backups`.")
        return 1
    backups.check_restorable(backup)
    print(f"Restoring {name}, the current state is saved first...")
    engine.dispose()
    result = backups.call("POST", f"backups/{name}/restore", json={"safety": True}).json()
    # An older backup is brought to this version of the database
    migrate = subprocess.run([sys.executable, "-m", "alembic", "upgrade", "head"], cwd=backups.BACKEND_DIR)
    if migrate.returncode != 0:
        print("The database was restored, but its migration failed (see above).")
        return 1
    print(f"Restored. The state before it is in the backup {result.get('saved')}.")
    print("Now restart the backend: docker compose restart backend")
    return 0


def main(args: list[str]) -> int:
    try:
        if args[:1] == ["https-off"]:
            return https_off()
        if args[:1] == ["backups"]:
            return list_backups()
        if args[:1] == ["restore"] and len(args) == 2:
            return restore(args[1])
    except HTTPException as exc:
        print(f"Error: {exc.detail}")
        return 1
    print(__doc__.strip())
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
