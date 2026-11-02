import json

import pytest

from app import __build__, __version__
from app.config import get_settings
from app.services.updates import release_key


@pytest.fixture
def updates_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(get_settings(), "updates_dir", tmp_path)
    return tmp_path


def write_state(folder, **state):
    base = {"status": "idle", "step": "", "checked_at": "2026-10-19T12:00:00Z", "sources": [], "last": None}
    (folder / "state.json").write_text(json.dumps({**base, **state}))


def source(name, kind="branch", version="9.0", build="20991231.0000", published=True):
    ref = f"refs/heads/{name}" if kind == "branch" else f"refs/tags/{name}"
    return {"name": name, "kind": kind, "ref": ref, "commit": "abc1234def", "version": version, "build": build,
            "published": published}


def test_release_order():
    assert release_key("1.1", "20261019.0001") > release_key("1.0", "20261018.0001")
    assert release_key("1.2.1", "20261019.0001") > release_key("1.2", "20261020.0001")
    assert release_key("1.0", "20261018.0002") > release_key("1.0", "20261018.0001")
    assert release_key("1.10", "1") > release_key("1.9", "2")


def test_unavailable_without_updater(client, updates_dir):
    data = client.get("/api/updates").json()
    assert (data["status"], data["version"], data["update_available"]) == ("unavailable", __version__, False)
    assert client.post("/api/updates/check").status_code == 409


def test_channels_from_tags(client, updates_dir):
    write_state(updates_dir, sources=[
        source("v9.0", "tag", "9.0", "1"),
        source("v9.1-beta.1", "tag", "9.1", "1"),
        # Newest tag, but its images are not published yet: not part of a channel
        source("v9.2-beta.1", "tag", "9.2", "1", published=False),
        source("main", version="9.2", build="2"),
    ])
    data = client.get("/api/updates").json()
    assert [(s["name"], s["kind"], s["tag"]) for s in data["sources"]] == [
        ("@stable", "channel", "v9.0"), ("@beta", "channel", "v9.1-beta.1"), ("main", "branch", None)]
    # Nothing picked yet: the stable channel
    assert (data["selected_source"], data["update_available"]) == ("@stable", True)
    assert client.post("/api/updates/install").status_code == 202
    assert json.loads((updates_dir / "request.json").read_text()) == {"action": "install", "ref": "refs/tags/v9.0"}


def test_sources_and_install(client, updates_dir):
    write_state(updates_dir, sources=[
        source("main"),
        source("old", version=__version__, build=__build__),
        source("building", published=False),
        source("empty", version="", build=""),
    ])
    data = client.get("/api/updates").json()
    assert [(s["newer"], s["published"]) for s in data["sources"]] == [(True, True), (False, True), (True, False),
                                                                        (False, True)]
    # No release tag: the stable channel doesn't exist yet
    assert (data["selected_source"], data["update_available"]) == ("@stable", False)
    assert client.get("/api/updates/status").json()["status"] == "idle"

    # Not newer, images not published yet, missing: nothing to install
    for name, code in (("old", 409), ("building", 409), ("nope", 404), ("@stable", 404)):
        settings = client.patch("/api/settings", json={"update_source": name}).json()
        assert settings["update_source"] == name
        data = client.get("/api/updates").json()
        assert (data["selected_source"], data["update_available"]) == (name, False)
        assert client.post("/api/updates/install").status_code == code
    assert not (updates_dir / "request.json").exists()

    # Empty: back to the stable channel
    assert client.patch("/api/settings", json={"update_source": ""}).json()["update_source"] is None
    client.patch("/api/settings", json={"update_source": "main"})
    assert client.get("/api/updates").json()["update_available"] is True
    assert client.post("/api/updates/install").status_code == 202
    assert json.loads((updates_dir / "request.json").read_text()) == {"action": "install", "ref": "refs/heads/main"}

    write_state(updates_dir, status="updating", step="download", progress=42)
    assert client.post("/api/updates/check").status_code == 409
    status = client.get("/api/updates/status").json()
    assert (status["step"], status["progress"]) == ("download", 42)


def test_check_request(client, updates_dir):
    write_state(updates_dir)
    assert client.post("/api/updates/check").status_code == 202
    assert json.loads((updates_dir / "request.json").read_text()) == {"action": "check"}


def test_admin_only(client, updates_dir):
    r = client.post("/api/users", json={"username": "mario", "email": "m@example.com", "password": "Password123",
                                        "role": "user"})
    assert r.status_code == 201
    client.post("/api/auth/logout")
    assert client.post("/api/auth/login", json={"username": "mario", "password": "Password123"}).status_code == 200
    write_state(updates_dir)
    assert client.get("/api/updates").status_code == 403
    assert client.get("/api/updates/status").status_code == 200
    assert client.post("/api/updates/check").status_code == 403


def test_pending_request_reads_as_running(client, updates_dir):
    write_state(updates_dir, sources=[source("main")])
    client.patch("/api/settings", json={"update_source": "main"})
    assert client.post("/api/updates/install").status_code == 202
    # The updater hasn't picked the request up yet
    assert client.get("/api/updates/status").json()["status"] == "updating"
    assert client.post("/api/updates/check").status_code == 409


def test_check_interval(client, updates_dir):
    assert client.get("/api/settings").json()["update_check_hours"] == 6
    assert client.patch("/api/settings", json={"update_check_hours": 24}).json()["update_check_hours"] == 24
    assert json.loads((updates_dir / "settings.json").read_text()) == {"check_hours": 24}
    assert client.patch("/api/settings", json={"update_check_hours": 0}).json()["update_check_hours"] == 0
    assert client.patch("/api/settings", json={"update_check_hours": 5}).status_code == 422


def test_check_error_kept_apart_from_install_result(client, updates_dir):
    # A result of the updater of version 1.3 has more fields
    last = {"result": "failed", "error": "start", "restart_required": True, "finished_at": "2026-10-24T10:00:00Z"}
    write_state(updates_dir, last=last, check_error={"detail": "Could not resolve host", "failed_at": "2026-10-24T11:00:00Z"})
    data = client.get("/api/updates").json()
    assert data["last"] == {"result": "failed", "error": "start", "detail": "", "finished_at": "2026-10-24T10:00:00Z"}
    assert data["check_error"]["detail"] == "Could not resolve host"
