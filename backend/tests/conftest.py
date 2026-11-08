import os

os.environ.setdefault("DATABASE_URL", "postgresql+psycopg://candidate:candidate@localhost:5432/candidate_test")

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, SQLModel

from app.features.auth import rate_limit
from app.features.settings import service as settings_service
from app.main import app
from app.shared.database import engine


@pytest.fixture(autouse=True)
def clean_db():
    SQLModel.metadata.drop_all(engine)
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        settings_service.ensure(session)
    rate_limit.reset()
    yield


ADMIN = {"username": "admin", "email": "admin@example.com", "password": "Password123", "language": "it"}


@pytest.fixture
def anon(tmp_path, monkeypatch):
    """Client without a session."""
    from app.core.config import get_settings

    monkeypatch.setattr(get_settings(), "upload_dir", tmp_path)
    return TestClient(app)


@pytest.fixture
def client(anon):
    """Client logged in as the first admin."""
    assert anon.post("/api/setup", json=ADMIN).status_code == 201
    return anon
