import json
import subprocess
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from app.config import get_settings
from app.services import backups

BACKUP = {"name": "candidate-20261102-030000-auto.tar.gz", "kind": "auto", "note": "", "created_at": "2026-11-02T03:00:00Z",
          "version": "2.0", "build": "1", "revision": "0022", "size": 1234}
NEWER = {**BACKUP, "name": "candidate-20261102-040000-manual.tar.gz", "kind": "manual", "revision": "9999"}


class FakeBackup(BaseHTTPRequestHandler):
    """The backup service: two backups, and a restore that takes a moment."""

    requests: list[tuple[str, str, dict]] = []
    restore_seconds = 0.3

    def log_message(self, *args):
        pass

    def reply(self, code, data=None, raw=None):
        body = raw if raw is not None else json.dumps(data).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/gzip" if raw is not None else "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def record(self):
        length = int(self.headers.get("Content-Length") or 0)
        data = json.loads(self.rfile.read(length) or b"{}")
        FakeBackup.requests.append((self.command, self.path, data))
        return data

    def do_GET(self):
        self.record()
        if self.path == "/status":
            return self.reply(200, {"settings": {"frequency": "daily", "hour": 3, "weekday": 0, "timezone": "UTC",
                                                 "keep": 7, "max_age_days": 0}, "running": None,
                                    "last_auto": {"result": "ok", "detail": "", "at": "2026-11-02T03:00:05Z"}})
        if self.path == "/backups":
            return self.reply(200, [NEWER, BACKUP])
        if self.path == f"/backups/{BACKUP['name']}/file":
            return self.reply(200, raw=b"archive")
        self.reply(404, {"detail": "backup not found"})

    def do_PUT(self):
        self.reply(200, self.record())

    def do_POST(self):
        data = self.record()
        if self.path.endswith("/restore"):
            time.sleep(FakeBackup.restore_seconds)
            return self.reply(200, {"restored": BACKUP["name"], "saved": "x"})
        self.reply(201, {**BACKUP, "kind": "manual", "note": data.get("note", "")})

    def do_DELETE(self):
        self.record()
        self.send_response(204)
        self.end_headers()


@pytest.fixture
def service(monkeypatch):
    server = ThreadingHTTPServer(("127.0.0.1", 0), FakeBackup)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    monkeypatch.setattr(get_settings(), "backup_url", f"http://127.0.0.1:{server.server_port}")
    # The migrations after a restore run on a database the tests build without them
    monkeypatch.setattr(backups.subprocess, "run", lambda *a, **k: subprocess.CompletedProcess(a, 0, "", ""))
    FakeBackup.requests.clear()
    yield FakeBackup
    server.shutdown()


def wait_restored():
    for _ in range(100):
        if not backups.restoring():
            return
        time.sleep(0.05)
    raise AssertionError("restore still running")


def test_list_settings_create_delete(client, service):
    data = client.get("/api/backups").json()
    assert [b["name"] for b in data["backups"]] == [NEWER["name"], BACKUP["name"]]
    assert data["settings"]["frequency"] == "daily" and data["last_auto"]["result"] == "ok"

    saved = client.put("/api/backups/settings", json={"frequency": "weekly", "hour": 4, "weekday": 6,
                                                      "timezone": "Europe/Rome", "keep": 3, "max_age_days": 30})
    assert saved.status_code == 200 and service.requests[-1][2]["weekday"] == 6
    assert client.put("/api/backups/settings", json={"frequency": "hourly"}).status_code == 422

    assert client.post("/api/backups", json={"note": "prima di provare"}).json()["note"] == "prima di provare"
    assert service.requests[-1][2] == {"kind": "manual", "note": "prima di provare"}
    assert client.delete(f"/api/backups/{BACKUP['name']}").status_code == 204

    download = client.get(f"/api/backups/{BACKUP['name']}/file")
    assert download.content == b"archive" and BACKUP["name"] in download.headers["content-disposition"]
    assert client.get("/api/backups/nope/file").status_code == 404


def test_unavailable_service(client, monkeypatch):
    monkeypatch.setattr(get_settings(), "backup_url", "http://127.0.0.1:1")
    assert client.get("/api/backups").status_code == 503


def test_restore_puts_app_in_maintenance(client, service):
    # A backup of a newer database revision is refused
    assert client.post(f"/api/backups/{NEWER['name']}/restore").status_code == 409
    assert client.post("/api/backups/nope/restore").status_code == 404

    assert client.post(f"/api/backups/{BACKUP['name']}/restore").status_code == 202
    # Meanwhile only the health check answers
    assert client.get("/api/applications").status_code == 503
    assert client.get("/api/health").json()["status"] == "restoring"
    wait_restored()
    assert ("POST", f"/backups/{BACKUP['name']}/restore", {"safety": True}) in service.requests
    assert client.get("/api/backups").json()["last_restore"]["result"] == "ok"
    assert client.get("/api/health").json()["status"] == "ok"


def test_restore_needs_no_ai_jobs(client, service):
    r = client.post("/api/applications/ai", data={"text": "Cerchiamo un Backend Developer Python a Milano."})
    assert r.status_code == 201
    r = client.post(f"/api/backups/{BACKUP['name']}/restore")
    assert r.status_code == 409 and "operazioni AI" in r.json()["detail"]


def test_admin_only(client, service):
    client.post("/api/users", json={"username": "mario", "email": "m@example.com", "password": "Password123",
                                    "role": "user"})
    client.post("/api/auth/logout")
    client.post("/api/auth/login", json={"username": "mario", "password": "Password123"})
    assert client.get("/api/backups").status_code == 403
    assert client.post(f"/api/backups/{BACKUP['name']}/restore").status_code == 403
