import io

from fastapi.testclient import TestClient
from PIL import Image

from app.main import app
from tests.conftest import ADMIN

USER = {"username": "Mario", "email": "mario@example.com", "password": "Segreta1234"}


def _login(username: str, password: str) -> TestClient:
    other = TestClient(app)
    assert other.post("/api/auth/login", json={"username": username, "password": password}).status_code == 200
    return other


def _image(fmt: str = "PNG", size=(400, 300)) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", size, "red").save(buf, fmt)
    return buf.getvalue()


def test_setup_only_once(anon):
    status = anon.get("/api/auth/status").json()
    assert status["setup_required"] is True and status["password_policy"]["password_min_length"] == 10
    assert anon.get("/api/applications").status_code == 401

    weak = anon.post("/api/auth/setup", json={**ADMIN, "password": "short"})
    assert weak.status_code == 422 and "10 caratteri" in weak.json()["detail"]

    created = anon.post("/api/auth/setup", json=ADMIN).json()
    assert created["user"]["role"] == "admin"
    assert len(created["recovery_key"]) == 29 and created["recovery_key"].count("-") == 5
    assert anon.get("/api/me").json()["username"] == "admin"

    assert anon.get("/api/auth/status").json()["setup_required"] is False
    assert anon.post("/api/auth/setup", json={**ADMIN, "username": "other", "email": "o@example.com"}).status_code == 409


def test_setup_claims_existing_data(anon):
    from sqlmodel import Session

    from app.db import engine
    from app.models import Application, Profile

    with Session(engine) as session:
        session.add(Application(title="Prima degli utenti"))
        session.add(Profile(full_name="Ivan"))
        session.commit()
    anon.post("/api/auth/setup", json=ADMIN)
    assert [a["title"] for a in anon.get("/api/applications").json()] == ["Prima degli utenti"]
    assert anon.get("/api/profile").json()["full_name"] == "Ivan"


def test_login_logout_and_lockout(client):
    client.patch("/api/settings", json={"max_login_attempts": 3, "lockout_minutes": 5})
    client.post("/api/auth/logout")
    assert client.get("/api/me").status_code == 401

    # Usernames are case-insensitive
    assert client.post("/api/auth/login", json={"username": "ADMIN", "password": "Password123"}).status_code == 200
    client.post("/api/auth/logout")

    for _ in range(3):
        r = client.post("/api/auth/login", json={"username": "admin", "password": "sbagliata"})
        assert r.status_code == 401 and r.json()["detail"] == "Username o password non corretti"
    r = client.post("/api/auth/login", json={"username": "admin", "password": "Password123"})
    assert r.status_code == 423 and "5 min" in r.json()["detail"]

    # Unknown username: same error as a wrong password
    assert client.post("/api/auth/login", json={"username": "nessuno", "password": "x"}).status_code == 401


def test_password_change_closes_other_sessions(client):
    other = _login("admin", "Password123")
    r = client.post("/api/me/password", json={"current_password": "sbagliata", "new_password": "NuovaPass99"})
    assert r.status_code == 403
    r = client.post("/api/me/password", json={"current_password": "Password123", "new_password": "nuovapass"})
    assert r.status_code == 422 and "maiuscola" in r.json()["detail"]
    assert client.post("/api/me/password",
                       json={"current_password": "Password123", "new_password": "NuovaPass99"}).status_code == 200
    assert client.get("/api/me").status_code == 200
    assert other.get("/api/me").status_code == 401


def test_recovery_key_reset(anon):
    key = anon.post("/api/auth/setup", json=ADMIN).json()["recovery_key"]
    anon.post("/api/auth/logout")

    r = anon.post("/api/auth/reset", json={"username": "admin", "recovery_key": "AAAA-BBBB", "new_password": "NuovaPass99"})
    assert r.status_code == 401
    # The key is also accepted without dashes and in lowercase
    r = anon.post("/api/auth/reset",
                  json={"username": "admin", "recovery_key": key.replace("-", "").lower(), "new_password": "NuovaPass99"})
    assert r.status_code == 200
    new_key = r.json()["recovery_key"]
    assert new_key != key and anon.get("/api/me").status_code == 200

    # A used key is no longer valid
    r = anon.post("/api/auth/reset", json={"username": "admin", "recovery_key": key, "new_password": "AltraPass99"})
    assert r.status_code == 401
    _login("admin", "NuovaPass99")

    # New key from settings, with password confirmation
    assert anon.post("/api/me/recovery-key", json={"password": "sbagliata"}).status_code == 403
    downloaded = anon.post("/api/me/recovery-key", json={"password": "NuovaPass99"}).json()["recovery_key"]
    assert anon.post("/api/auth/reset", json={"username": "admin", "recovery_key": new_key,
                                              "new_password": "AltraPass99"}).status_code == 401
    assert anon.post("/api/auth/reset", json={"username": "admin", "recovery_key": downloaded,
                                              "new_password": "AltraPass99"}).status_code == 200


def test_admin_manages_users(client):
    created = client.post("/api/users", json=USER)
    assert created.status_code == 201
    user, key = created.json()["user"], created.json()["recovery_key"]
    assert (user["username"], user["role"]) == ("mario", "user") and key

    assert client.post("/api/users", json={**USER, "email": "x@example.com"}).json()["detail"] == "Username già in uso"
    assert client.post("/api/users", json={**USER, "username": "luigi"}).json()["detail"] == "Email già in uso"
    assert client.post("/api/users", json={**USER, "username": "a b"}).status_code == 422

    mario = _login("mario", USER["password"])
    # Regular users can't manage users or system settings
    assert mario.get("/api/users").status_code == 403
    assert mario.post("/api/users", json={**USER, "username": "luigi", "email": "l@example.com"}).status_code == 403
    assert mario.patch("/api/settings", json={"llm_enabled": False}).status_code == 403
    assert mario.get("/api/settings").status_code == 200
    assert mario.patch("/api/me", json={"theme": "dark"}).json()["theme"] == "dark"

    # Admin changes role and password: the user's sessions are closed
    r = client.patch(f"/api/users/{user['id']}", json={"role": "admin", "password": "Reimpostata1"})
    assert r.json()["role"] == "admin"
    assert mario.get("/api/me").status_code == 401
    _login("mario", "Reimpostata1")

    assert client.delete(f"/api/users/{client.get('/api/me').json()['id']}").status_code == 409
    assert client.delete(f"/api/users/{user['id']}").status_code == 204
    assert [u["username"] for u in client.get("/api/users").json()] == ["admin"]


def test_last_admin_stays(client):
    me = client.get("/api/me").json()
    r = client.patch(f"/api/users/{me['id']}", json={"role": "user"})
    assert r.status_code == 409 and r.json()["detail"] == "Deve restare almeno un amministratore"


def test_data_is_private(client):
    app_id = client.post("/api/applications", json={"title": "Dell'admin"}).json()["id"]
    client.post("/api/events", json={"application_id": app_id, "type": "interview", "occurred_on": "2026-11-02",
                                     "title": "Colloquio"})
    event_id = client.get("/api/events").json()[0]["id"]
    client.patch("/api/profile", json={"full_name": "Admin"})

    client.post("/api/users", json=USER)
    mario = _login("mario", USER["password"])
    assert mario.get("/api/applications").json() == []
    assert mario.get("/api/events").json() == []
    assert mario.get("/api/profile").json()["full_name"] is None
    assert mario.get(f"/api/applications/{app_id}").status_code == 404
    assert mario.patch(f"/api/applications/{app_id}", json={"title": "x"}).status_code == 404
    assert mario.delete(f"/api/events/{event_id}").status_code == 404
    assert mario.post("/api/events", json={"application_id": app_id, "type": "note", "occurred_on": "2026-11-02",
                                           "title": "x"}).status_code == 404
    assert mario.get(f"/api/users/{client.get('/api/me').json()['id']}/avatar").status_code == 404

    mario.post("/api/applications", json={"title": "Di Mario"})
    assert [a["title"] for a in client.get("/api/applications").json()] == ["Dell'admin"]


def test_deleting_user_removes_data(client, tmp_path):
    client.post("/api/users", json=USER)
    mario = _login("mario", USER["password"])
    mario.post("/api/applications", json={"title": "Di Mario"})
    mario.put("/api/me/avatar", files={"file": ("me.png", _image(), "image/png")})
    mario_id = mario.get("/api/me").json()["id"]
    assert (tmp_path / f"user_{mario_id}" / "avatar.webp").exists()

    client.delete(f"/api/users/{mario_id}")
    assert not (tmp_path / f"user_{mario_id}").exists()

    from sqlmodel import Session, select

    from app.db import engine
    from app.models import Application

    with Session(engine) as session:
        assert session.exec(select(Application)).all() == []


def test_avatar(client):
    assert client.get("/api/me/avatar").status_code == 404
    r = client.put("/api/me/avatar", files={"file": ("me.jpg", _image("JPEG"), "image/jpeg")})
    assert r.status_code == 200 and r.json()["has_avatar"] is True

    avatar = client.get("/api/me/avatar")
    assert avatar.headers["content-type"] == "image/webp"
    assert Image.open(io.BytesIO(avatar.content)).size == (256, 256)

    r = client.put("/api/me/avatar", files={"file": ("me.png", b"non un'immagine", "image/png")})
    assert r.status_code == 422
    assert client.delete("/api/me/avatar").json()["has_avatar"] is False
    assert client.get("/api/me/avatar").status_code == 404


def test_profile_update_checks_uniqueness(client):
    client.post("/api/users", json=USER)
    assert client.patch("/api/me", json={"username": "mario"}).status_code == 409
    assert client.patch("/api/me", json={"username": "Capo", "email": "Capo@Example.com"}).json()["username"] == "capo"
    _login("capo", ADMIN["password"])


def test_security_policy_from_settings(client):
    client.patch("/api/settings", json={"password_min_length": 12, "password_require_symbol": True,
                                        "password_require_uppercase": False})
    r = client.post("/api/users", json={**USER, "password": "abcdefgh1"})
    assert r.status_code == 422
    assert r.json()["detail"] == "La password deve avere almeno 12 caratteri, un simbolo"
    assert client.post("/api/users", json={**USER, "password": "abcdefgh1234!"}).status_code == 201
    policy = client.get("/api/auth/status").json()["password_policy"]
    assert (policy["password_min_length"], policy["password_require_symbol"]) == (12, True)
