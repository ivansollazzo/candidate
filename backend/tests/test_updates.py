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
    base = {"status": "idle", "step": "", "checked_at": "2026-10-19T12:00:00Z", "branches": [], "last": None}
    (folder / "state.json").write_text(json.dumps({**base, **state}))


def branch(name, version="9.0", build="20991231.0000", published=True):
    return {"name": name, "commit": "abc1234def", "version": version, "build": build, "published": published}


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
        branch("main"),
        branch("old", version=__version__, build=__build__),
        branch("building", published=False),
        branch("empty", version="", build=""),
        branch("stable"),
    ])
    data = client.get("/api/updates").json()
    assert [(b["newer"], b["published"]) for b in data["branches"]] == [(True, True), (False, True), (True, False),
                                                                         (False, True), (True, True)]
    # Nothing picked yet: the stable branch
    assert (data["selected_branch"], data["update_available"]) == ("stable", True)
    assert client.get("/api/updates/status").json()["status"] == "idle"

    # Not newer, images not published yet, missing: nothing to install
    for name, code in (("old", 409), ("building", 409), ("nope", 404)):
        settings = client.patch("/api/settings", json={"update_branch": name}).json()
        assert settings["update_branch"] == name
        data = client.get("/api/updates").json()
        assert (data["selected_branch"], data["update_available"]) == (name, False)
        assert client.post("/api/updates/install").status_code == code
    assert not (updates_dir / "request.json").exists()

    # Empty: back to the stable branch
    assert client.patch("/api/settings", json={"update_branch": ""}).json()["update_branch"] is None
    client.patch("/api/settings", json={"update_branch": "main"})
    assert client.get("/api/updates").json()["update_available"] is True
    assert client.post("/api/updates/install").status_code == 202
    assert json.loads((updates_dir / "request.json").read_text()) == {"action": "install", "branch": "main"}

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
    write_state(updates_dir, branches=[branch("main")])
    client.patch("/api/settings", json={"update_branch": "main"})
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
    last = {"result": "failed", "error": "start", "detail": "", "finished_at": "2026-10-24T10:00:00Z"}
    write_state(updates_dir, last=last, check_error={"detail": "Could not resolve host", "failed_at": "2026-10-24T11:00:00Z"})
    data = client.get("/api/updates").json()
    assert data["last"] == last
    assert data["check_error"]["detail"] == "Could not resolve host"


def test_install_needs_no_ai_jobs(client, updates_dir):
    from app.services import updates

    write_state(updates_dir, branches=[branch("stable")])
    r = client.post("/api/applications/ai", data={"text": "Cerchiamo un Backend Developer Python a Milano."})
    assert r.status_code == 201
    assert client.get("/api/updates").json()["active_jobs"] == 1
    r = client.post("/api/updates/install")
    assert r.status_code == 409 and "operazioni AI" in r.json()["detail"]
    assert not (updates_dir / "request.json").exists()

    [job] = client.get("/api/jobs").json()
    client.delete(f"/api/jobs/{job['id']}")
    assert client.get("/api/updates").json()["active_jobs"] == 0
    assert client.post("/api/updates/install").status_code == 202
    # No job starts until the update is over
    assert updates.installing() is True
