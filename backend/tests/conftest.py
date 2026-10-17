import os

os.environ.setdefault("DATABASE_URL", "postgresql+psycopg://candidate:candidate@localhost:5432/candidate_test")

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlmodel import SQLModel  # noqa: E402

from app.db import engine  # noqa: E402
from app.main import app  # noqa: E402


@pytest.fixture(autouse=True)
def clean_db():
    SQLModel.metadata.drop_all(engine)
    SQLModel.metadata.create_all(engine)
    yield


ADMIN = {"username": "admin", "email": "admin@example.com", "password": "Password123", "language": "it"}


@pytest.fixture
def anon(tmp_path, monkeypatch):
    """Client without a session."""
    from app.config import get_settings

    monkeypatch.setattr(get_settings(), "upload_dir", tmp_path)
    return TestClient(app)


@pytest.fixture
def client(anon):
    """Client logged in as the first admin."""
    assert anon.post("/api/auth/setup", json=ADMIN).status_code == 201
    return anon
