"""Backups of Candidate: the database and the files of the backend (CVs, profile photos, attachments).

Runs as its own service (docker-compose.yml) and answers on port 8080 inside the Compose network only, to the
backend (Settings › Backup) and to the updater (a backup before every update, a restore when one fails).

A backup is one file in /backups, candidate-<date>-<time>-<kind>.tar.gz, with:
  manifest.json  kind, note, date, release and database revision
  database.sql   pg_dump of the database
  files/         the data folder of the backend (/app/data)
Kinds: auto (scheduled), manual, update (before an update), restore (before a restore). Only automatic
backups are deleted by the cleanup rules; the others stay until deleted by hand.

API (JSON):
  GET    /status                  settings, running operation, result of the last automatic backup
  PUT    /settings                {"frequency": "off|daily|weekly", "hour": 0-23, "weekday": 0-6 (Monday 0),
                                  "timezone": "Europe/Rome", "keep": 7, "max_age_days": 0}
  GET    /backups                 list, newest first
  POST   /backups                 {"kind": "manual|update", "note": "..."}: waits for the backup and returns it
  DELETE /backups/<name>
  GET    /backups/<name>/file     the archive
  POST   /backups/<name>/restore  {"safety": true}: database and files go back to that backup; with safety,
                                  the current state is saved first
"""

import json
import logging
import os
import re
import shutil
import subprocess
import tarfile
import tempfile
import threading
import time
import urllib.request
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

BACKUPS = Path(os.environ.get("BACKUP_DIR", "/backups"))
DATA = Path(os.environ.get("DATA_DIR", "/app/data"))
BACKEND_URL = os.environ.get("BACKEND_URL", "http://backend:8000")
PORT = int(os.environ.get("BACKUP_PORT", "8080"))
SETTINGS_FILE = BACKUPS / "settings.json"
STATE_FILE = BACKUPS / "state.json"
NAME = re.compile(r"^candidate-\d{8}-\d{6}-(auto|manual|update|restore)\.tar\.gz$")
KINDS = ("auto", "manual", "update", "restore")
# The hour is in the time zone of the admin who saved the settings (sent by the browser)
DEFAULTS = {"frequency": "daily", "hour": 3, "weekday": 0, "timezone": "UTC", "keep": 7, "max_age_days": 0}

logging.basicConfig(level=logging.INFO, format="[backup] %(message)s")
log = logging.getLogger("backup")

# One operation at a time: a restore must not run while a backup is being written, and the other way round
_lock = threading.Lock()
_running: dict | None = None
_manifests: dict[str, tuple[float, dict]] = {}


class Failure(Exception):
    pass


def now() -> datetime:
    return datetime.now(timezone.utc)


def iso(moment: datetime) -> str:
    return moment.strftime("%Y-%m-%dT%H:%M:%SZ")


def read_json(path: Path, default):
    try:
        return json.loads(path.read_text())
    except (OSError, ValueError):
        return default


def write_json(path: Path, data) -> None:
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data))
    tmp.replace(path)


def settings() -> dict:
    return {**DEFAULTS, **read_json(SETTINGS_FILE, {})}


def state() -> dict:
    return read_json(STATE_FILE, {})


def run(command: list[str], **kwargs) -> subprocess.CompletedProcess:
    result = subprocess.run(command, capture_output=True, text=True, **kwargs)
    if result.returncode != 0:
        raise Failure((result.stderr or result.stdout).strip()[-2000:] or f"{command[0]} failed")
    return result


def psql(sql: str) -> str:
    return run(["psql", "-X", "-q", "-t", "-A", "-v", "ON_ERROR_STOP=1", "-c", sql]).stdout.strip()


def health() -> dict:
    try:
        with urllib.request.urlopen(f"{BACKEND_URL}/api/health", timeout=5) as response:
            return json.load(response)
    except (OSError, ValueError):
        return {}  # backend stopped or restarting (e.g. during an update)


def release() -> tuple[str, str]:
    data = health()
    return data.get("version", ""), data.get("build", "")


# --- Backups -------------------------------------------------------------------------------------------


def manifest(path: Path) -> dict:
    """Manifest of a backup, read once per file: it is the first member of the archive."""
    mtime = path.stat().st_mtime
    cached = _manifests.get(path.name)
    if cached and cached[0] == mtime:
        return cached[1]
    try:
        with tarfile.open(path, "r:gz") as archive:
            data = json.load(archive.extractfile("manifest.json"))
    except (OSError, KeyError, ValueError, tarfile.TarError):
        data = {"kind": NAME.match(path.name).group(1), "broken": True}
    data = {**data, "name": path.name, "size": path.stat().st_size}
    _manifests[path.name] = (mtime, data)
    return data


def backups() -> list[dict]:
    files = [path for path in BACKUPS.glob("candidate-*.tar.gz") if NAME.match(path.name)]
    return sorted((manifest(path) for path in files), key=lambda item: item["name"], reverse=True)


def find(name: str) -> Path:
    path = BACKUPS / name
    if not NAME.match(name) or not path.is_file():
        raise Failure("backup not found")
    return path


def create(kind: str, note: str = "") -> dict:
    """Dump the database and pack it with the data folder. The archive appears only once complete."""
    started = now()
    name = f"candidate-{started:%Y%m%d-%H%M%S}-{kind}.tar.gz"
    work = Path(tempfile.mkdtemp(dir=BACKUPS, prefix=".work-"))
    try:
        dump = work / "database.sql"
        with dump.open("w") as out:
            result = subprocess.run(["pg_dump", "--no-owner", "--no-privileges"], stdout=out,
                                    stderr=subprocess.PIPE, text=True)
        if result.returncode != 0:
            raise Failure(result.stderr.strip()[-2000:] or "pg_dump failed")
        version, build = release()
        info = {
            "kind": kind, "note": note, "created_at": iso(started), "version": version, "build": build,
            "revision": psql("SELECT version_num FROM alembic_version") or None,
        }
        (work / "manifest.json").write_text(json.dumps(info))
        partial = work / name
        with tarfile.open(partial, "w:gz", compresslevel=6) as archive:
            archive.add(work / "manifest.json", "manifest.json")
            archive.add(dump, "database.sql")
            if DATA.is_dir():
                archive.add(DATA, "files", filter=lambda member: None if member.name.startswith("files/.") else member)
        partial.replace(BACKUPS / name)
        log.info("backup %s written", name)
        return manifest(BACKUPS / name)
    finally:
        shutil.rmtree(work, ignore_errors=True)


def restore(name: str, safety: bool) -> dict:
    """Put database and data folder back as they were in the backup."""
    path = find(name)
    saved = create("restore", name) if safety else None
    work = Path(tempfile.mkdtemp(dir=BACKUPS, prefix=".work-"))
    try:
        with tarfile.open(path, "r:gz") as archive:
            archive.extractall(work, filter="data")
        if not (work / "database.sql").is_file():
            raise Failure("the backup has no database")
        # Nobody else may use the database while it is replaced
        psql("SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
             "WHERE datname = current_database() AND pid <> pg_backend_pid()")
        psql("DROP SCHEMA public CASCADE; CREATE SCHEMA public;")
        with (work / "database.sql").open() as dump:
            run(["psql", "-X", "-q", "-v", "ON_ERROR_STOP=1"], stdin=dump)
        if DATA.is_dir():
            files = work / "files"
            # The entries of the data folder are swapped one by one: the folder itself is a mounted volume
            for entry in DATA.iterdir():
                if not entry.name.startswith("."):
                    shutil.rmtree(entry) if entry.is_dir() and not entry.is_symlink() else entry.unlink()
            if files.is_dir():
                for entry in files.iterdir():
                    shutil.move(str(entry), DATA / entry.name)
        log.info("restored %s", name)
        return {"restored": name, "saved": saved["name"] if saved else None}
    finally:
        shutil.rmtree(work, ignore_errors=True)


def clean() -> None:
    """Cleanup rules apply to automatic backups only."""
    rules = settings()
    automatic = [item for item in backups() if item.get("kind") == "auto"]
    keep = max(int(rules.get("keep") or 0), 1)
    doomed = automatic[keep:]
    days = int(rules.get("max_age_days") or 0)
    if days > 0:
        limit = iso(now() - timedelta(days=days))
        doomed += [item for item in automatic[:keep] if item.get("created_at", "") < limit]
    for item in doomed:
        (BACKUPS / item["name"]).unlink(missing_ok=True)
        log.info("backup %s removed by the cleanup rules", item["name"])


def operation(kind: str, target, *args):
    """Run one operation at a time, tracked in /status."""
    global _running
    if not _lock.acquire(blocking=False):
        raise Failure("busy")
    _running = {"operation": kind, "started_at": iso(now())}
    try:
        return target(*args)
    finally:
        _running = None
        _lock.release()


# --- Schedule ------------------------------------------------------------------------------------------


def last_due(rules: dict, moment: datetime) -> datetime | None:
    """The latest scheduled time not after moment, in UTC."""
    if rules["frequency"] not in ("daily", "weekly"):
        return None
    try:
        zone = ZoneInfo(str(rules.get("timezone") or "UTC"))
    except (ZoneInfoNotFoundError, ValueError):
        zone = timezone.utc
    moment = moment.astimezone(zone)
    due = moment.replace(hour=int(rules["hour"]) % 24, minute=0, second=0, microsecond=0)
    if rules["frequency"] == "daily":
        return (due if due <= moment else due - timedelta(days=1)).astimezone(timezone.utc)
    due -= timedelta(days=(due.weekday() - int(rules["weekday"])) % 7)
    return (due if due <= moment else due - timedelta(days=7)).astimezone(timezone.utc)


def scheduler() -> None:
    while True:
        try:
            rules, current = settings(), state()
            due = last_due(rules, now())
            if "last_auto_at" not in current:
                # First start: the first automatic backup is at the next scheduled time, not right away
                write_json(STATE_FILE, {**current, "last_auto_at": iso(now())})
            # Only with the backend up: at start it migrates the database, and while it is down nothing changes
            elif due and current["last_auto_at"] < iso(due) and not _lock.locked() and health().get("status") == "ok":
                result = None
                try:
                    operation("backup", create, "auto")
                    result = {"result": "ok", "detail": ""}
                    clean()
                except Failure as exc:
                    if str(exc) != "busy":  # busy: another operation started meanwhile, try again shortly
                        log.error("automatic backup failed: %s", exc)
                        result = {"result": "failed", "detail": str(exc)}
                # A failed backup isn't retried at once: the next one is at the next scheduled time
                if result:
                    write_json(STATE_FILE, {**state(), "last_auto_at": iso(now()), "last_auto": {**result, "at": iso(now())}})
        except Exception:
            log.exception("scheduler error")
        time.sleep(30)


# --- HTTP ----------------------------------------------------------------------------------------------


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def reply(self, code: int, data=None) -> None:
        body = json.dumps(data).encode() if data is not None else b""
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def body(self) -> dict:
        length = int(self.headers.get("Content-Length") or 0)
        try:
            return json.loads(self.rfile.read(length) or b"{}")
        except ValueError:
            return {}

    def handle_errors(self, action) -> None:
        try:
            action()
        except Failure as exc:
            code = 409 if str(exc) == "busy" else 404 if str(exc) == "backup not found" else 500
            self.reply(code, {"detail": str(exc)})
        except Exception as exc:
            log.exception("request failed")
            self.reply(500, {"detail": str(exc)})

    def do_GET(self):
        parts = self.path.strip("/").split("/")
        if parts == ["status"]:
            return self.reply(200, {**state(), "settings": settings(), "running": _running})
        if parts == ["backups"]:
            return self.reply(200, backups())
        if len(parts) == 3 and parts[0] == "backups" and parts[2] == "file":
            return self.handle_errors(lambda: self.send_file(find(parts[1])))
        self.reply(404, {"detail": "not found"})

    def send_file(self, path: Path) -> None:
        self.send_response(200)
        self.send_header("Content-Type", "application/gzip")
        self.send_header("Content-Length", str(path.stat().st_size))
        self.end_headers()
        with path.open("rb") as source:
            shutil.copyfileobj(source, self.wfile)

    def do_PUT(self):
        if self.path.strip("/") != "settings":
            return self.reply(404, {"detail": "not found"})
        allowed = {key: value for key, value in self.body().items() if key in DEFAULTS}
        write_json(SETTINGS_FILE, {**settings(), **allowed})
        self.reply(200, settings())

    def do_POST(self):
        parts = self.path.strip("/").split("/")
        data = self.body()
        if parts == ["backups"]:
            kind = data.get("kind", "manual")
            if kind not in ("manual", "update"):
                return self.reply(422, {"detail": "kind"})
            return self.handle_errors(lambda: self.reply(201, operation("backup", create, kind, str(data.get("note", "")))))
        if len(parts) == 3 and parts[0] == "backups" and parts[2] == "restore":
            return self.handle_errors(lambda: self.reply(200, operation(
                "restore", restore, parts[1], bool(data.get("safety", True)))))
        self.reply(404, {"detail": "not found"})

    def do_DELETE(self):
        parts = self.path.strip("/").split("/")
        if len(parts) == 2 and parts[0] == "backups":
            def delete():
                find(parts[1]).unlink()
                self.reply(204)
            return self.handle_errors(delete)
        self.reply(404, {"detail": "not found"})


def main() -> None:
    BACKUPS.mkdir(parents=True, exist_ok=True)
    for leftover in BACKUPS.glob(".work-*"):
        shutil.rmtree(leftover, ignore_errors=True)  # an operation cut off by a restart
    threading.Thread(target=scheduler, name="scheduler", daemon=True).start()
    log.info("listening on port %s, backups in %s", PORT, BACKUPS)
    ThreadingHTTPServer(("0.0.0.0", PORT), Handler).serve_forever()


if __name__ == "__main__":
    main()
