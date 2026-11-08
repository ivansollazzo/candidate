"""Single row of system settings."""

from datetime import datetime

import sqlalchemy as sa
from sqlmodel import Field, SQLModel

from app.shared.database import bool_field, int_field, json_list, json_object, timestamp


class AppSettings(SQLModel, table=True):
    """System settings (single row), editable by the admin."""

    __tablename__ = "app_settings"

    id: int | None = Field(default=None, primary_key=True)
    llm_enabled: bool = bool_field(True)
    # auto, cuda, rocm, vulkan, cpu; read by the llm service
    llm_accelerator: str = Field(default="auto", sa_type=sa.String(10), sa_column_kwargs={"server_default": "auto"})

    # Updates: followed branch, None = "stable", and hours between checks (0 = only on request)
    update_branch: str | None = Field(default=None, sa_type=sa.String(200))
    update_check_hours: int = int_field(6)

    # Security policy
    password_min_length: int = int_field(10)
    password_require_uppercase: bool = bool_field(True)
    password_require_digit: bool = bool_field(True)
    password_require_symbol: bool = bool_field(False)
    # Sessions expire after this many hours without using the app
    session_hours: int = int_field(168)
    # Account lock after failed sign-ins or recovery keys (off by default)
    account_lockout_enabled: bool = bool_field(False)
    max_login_attempts: int = int_field(5)
    lockout_minutes: int = int_field(15)
    # Per-IP limit on failed sign-ins and recovery keys, whatever the account (off by default)
    ip_limit_enabled: bool = bool_field(False)
    ip_max_attempts: int = int_field(20)
    ip_block_minutes: int = int_field(15)
    # Session signing key, generated on first run
    secret_key: str | None = Field(default=None, sa_type=sa.String(128))

    # HTTPS served by Caddy (https/service.py): off, internal (certificate signed by the app's own authority)
    # or custom (certificates uploaded by the admin), for the hosts listed
    https_mode: str = Field(default="off", sa_type=sa.String(10), sa_column_kwargs={"server_default": "off"})
    https_hosts: list[str] = json_list()
    # Uploaded certificates: [{"cert": PEM with chain, "key": PEM}]
    https_certs: list[dict] = json_list()
    # Internal mode: the authority ({"cert", "key"}) and the certificate it issued ({"cert", "key", "hosts"})
    https_ca: dict | None = json_object()
    https_leaf: dict | None = json_object()

    updated_at: datetime = timestamp(onupdate=True)
