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
    base = {"status": "idle", "step": "", "branch": "main", "commit": "abc1234", "checked_at": "2026-10-19T12:00:00Z",
            "branches": [], "last": None}
    (folder / "state.json").write_text(json.dumps({**base, **state}))


def test_release_order():
    assert release_key("1.1", "20261019.0001") > release_key("1.0", "20261018.0001")
    assert release_key("1.2.1", "20261019.0001") > release_key("1.2", "20261020.0001")
    assert release_key("1.0", "20261018.0002") > release_key("1.0", "20261018.0001")
    assert release_key("1.10", "1") > release_key("1.9", "2")


def test_unavailable_without_updater(client, updates_dir):
    data = client.get("/api/updates").json()
    assert (data["status"], data["version"], data["update_available"]) == ("unavailable", __version__, False)
    assert client.post("/api/updates/check").status_code == 409


def test_branches_and_install(client, updates_dir):
    write_state(updates_dir, branches=[
        {"name": "main", "version": "9.0", "build": "20991231.0000", "commit": "1111111"},
        {"name": "old", "version": __version__, "build": __build__, "commit": "2222222"},
        {"name": "empty", "version": "", "build": "", "commit": "3333333"},
    ])
    data = client.get("/api/updates").json()
    assert [b["newer"] for b in data["branches"]] == [True, False, False]
    assert data["update_available"] is True
    assert client.get("/api/updates/status").json()["status"] == "idle"

    # A selected branch without a newer release, or a missing one: nothing to install
    for name, code in (("old", 409), ("nope", 404)):
        settings = client.patch("/api/settings", json={"update_branch": name}).json()
        assert settings["update_branch"] == name
        data = client.get("/api/updates").json()
        assert (data["selected_branch"], data["update_available"]) == (name, False)
        assert client.post("/api/updates/install").status_code == code
    assert not (updates_dir / "request.json").exists()

    client.patch("/api/settings", json={"update_branch": "old"})
    # Back to the checked-out branch
    assert client.patch("/api/settings", json={"update_branch": ""}).json()["update_branch"] is None
    assert client.get("/api/updates").json()["selected_branch"] == "main"
    assert client.post("/api/updates/install").status_code == 202
    assert json.loads((updates_dir / "request.json").read_text()) == {"action": "install", "branch": "main"}

    write_state(updates_dir, status="updating", step="build", progress=42)
    assert client.post("/api/updates/check").status_code == 409
    status = client.get("/api/updates/status").json()
    assert (status["step"], status["progress"]) == ("build", 42)


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
    write_state(updates_dir, branches=[{"name": "main", "version": "9.0", "build": "1", "commit": "1111111"}])
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
