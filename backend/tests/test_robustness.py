"""Every route, with wrong or missing input and as every kind of user, answers with an error the app can show
(4xx), never with a server error."""

import re

import pytest
from fastapi.testclient import TestClient

from app.config import get_settings
from app.main import app
from tests.conftest import ADMIN

BODIES = [None, {}, "not json", {"ids": "x", "status": 5, "mode": "nope", "hosts": [None]}, [1, 2],
          {"ids": [0, -1, 2**40], "status": "interview"}, {"title": "x" * 100_000}]


def routes():
    for path, methods in app.openapi()["paths"].items():
        for method in methods:
            yield method.upper(), path


def concrete(path: str) -> list[str]:
    """Path parameters as an unknown id, a wrong type and a traversal attempt."""
    if "{" not in path:
        return [path]
    return [re.sub(r"\{[^}]+\}", value, path) for value in ("999999", "nope", "..%2F..%2Fetc%2Fpasswd", "-1")]


def sweep(client: TestClient, sign_in) -> list[str]:
    failures = []
    for method, path in routes():
        for url in concrete(path):
            for body in BODIES:
                kwargs = {"content": body} if isinstance(body, str) else {} if body is None else {"json": body}
                r = client.request(method, url, **kwargs)
                if r.status_code >= 500 and r.status_code != 503:
                    failures.append(f"{method} {url} {body!r:.40}: {r.status_code} {r.text[:120]}")
                # Some routes end the session (sign out, HTTPS switch): start a new one
                sign_in()
    return failures


@pytest.fixture
def offline(monkeypatch, tmp_path):
    # The backup service and the updater aren't there: the routes that need them answer 503 or 409
    monkeypatch.setattr(get_settings(), "backup_url", "http://127.0.0.1:1")


def signed_in(username: str, password: str) -> tuple[TestClient, callable]:
    """A client that shows server errors as responses, and a function that signs it in again when needed."""
    user = TestClient(app, raise_server_exceptions=False)

    def sign_in():
        if user.get("/api/me").status_code == 401:
            user.cookies.clear()
            assert user.post("/api/session", json={"username": username, "password": password}).status_code == 200
    sign_in()
    return user, sign_in


def test_admin_sweep(client, offline):
    admin, sign_in = signed_in(ADMIN["username"], ADMIN["password"])
    seen = []
    admin.event_hooks["response"].append(lambda r: seen.append(r.status_code))
    assert sweep(admin, sign_in) == []
    # The sweep really reached the routes, signed in
    assert sum(code < 300 for code in seen) > 50 and sum(code == 422 for code in seen) > 50


def test_user_and_anonymous_sweep(client, offline):
    client.post("/api/users", json={"username": "mario", "email": "m@example.com", "password": "Password123",
                                    "role": "user", "language": "it"})
    assert sweep(*signed_in("mario", "Password123")) == []
    anonymous = TestClient(app, raise_server_exceptions=False)
    assert sweep(anonymous, anonymous.cookies.clear) == []
