"""Safety net for the restructuring: the API contract, the database schema and the import rules."""

import json
import os
from pathlib import Path

from alembic.autogenerate import compare_metadata
from alembic.command import upgrade
from alembic.config import Config
from alembic.runtime.migration import MigrationContext
from importlinter.cli import lint_imports
from sqlalchemy import create_engine
from sqlmodel import SQLModel

from app.core.config import get_settings
from app.main import app
from app.shared.database import engine

BACKEND = Path(__file__).resolve().parents[1]
OPENAPI = Path(__file__).with_name("openapi.json")


def test_openapi_unchanged():
    """Every route, parameter and schema as published; UPDATE_OPENAPI=1 rewrites the reference."""
    current = app.openapi()
    if os.environ.get("UPDATE_OPENAPI") == "1":
        OPENAPI.write_text(json.dumps(current, indent=1, sort_keys=True, ensure_ascii=False) + "\n")
    assert current == json.loads(OPENAPI.read_text())


def test_migrations_match_models(monkeypatch):
    """The migrations build exactly the schema the models describe."""
    name = f"{engine.url.database}_migrations"
    url = engine.url.set(database=name)
    server = create_engine(engine.url.set(database="postgres"), isolation_level="AUTOCOMMIT")
    with server.connect() as conn:
        conn.exec_driver_sql(f'DROP DATABASE IF EXISTS "{name}"')
        conn.exec_driver_sql(f'CREATE DATABASE "{name}"')
    migrated = create_engine(url)
    try:
        monkeypatch.setattr(get_settings(), "database_url", url.render_as_string(hide_password=False))
        config = Config()
        config.set_main_option("script_location", str(BACKEND / "alembic"))
        upgrade(config, "head")
        with migrated.connect() as conn:
            context = MigrationContext.configure(conn, opts={"compare_type": True})
            assert compare_metadata(context, SQLModel.metadata) == []
    finally:
        migrated.dispose()
        with server.connect() as conn:
            conn.exec_driver_sql(f'DROP DATABASE IF EXISTS "{name}"')
        server.dispose()


def test_import_rules(monkeypatch):
    """The rules in backend/.importlinter."""
    monkeypatch.chdir(BACKEND)
    assert lint_imports(config_filename=str(BACKEND / ".importlinter"), no_cache=True, no_logo=True) == 0
