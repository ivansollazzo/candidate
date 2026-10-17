"""users with roles, per-user data and security policy

Revision ID: 0009
Revises: 0008
Create Date: 2026-10-17
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0009"
down_revision: str | None = "0008"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

POLICY = {
    "password_min_length": (sa.Integer(), "10"),
    "password_require_uppercase": (sa.Boolean(), sa.true()),
    "password_require_digit": (sa.Boolean(), sa.true()),
    "password_require_symbol": (sa.Boolean(), sa.false()),
    "session_hours": (sa.Integer(), "12"),
    "max_login_attempts": (sa.Integer(), "5"),
    "lockout_minutes": (sa.Integer(), "15"),
}
# Preferences moved from global settings to the user
PREFERENCES = {
    "language": (sa.String(5), "it"),
    "theme": (sa.String(10), "system"),
    "onboarded": (sa.Boolean(), sa.false()),
}


def upgrade() -> None:
    op.create_table(
        "app_user",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("username", sa.String(50), nullable=False),
        sa.Column("email", sa.String(255), nullable=False, unique=True),
        sa.Column("password_hash", sa.String(255), nullable=False),
        sa.Column("recovery_key_hash", sa.String(255), nullable=False),
        sa.Column("role", sa.String(10), nullable=False),
        *(sa.Column(name, type_, server_default=default, nullable=False)
          for name, (type_, default) in PREFERENCES.items()),
        sa.Column("avatar_path", sa.String(), nullable=True),
        sa.Column("session_version", sa.Integer(), server_default="0", nullable=False),
        sa.Column("failed_logins", sa.Integer(), server_default="0", nullable=False),
        sa.Column("locked_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_app_user_username", "app_user", ["username"], unique=True)

    for table, unique in (("application", False), ("profile", True)):
        op.add_column(table, sa.Column("user_id", sa.Integer(), nullable=True))
        op.create_foreign_key(f"{table}_user_id_fkey", table, "app_user", ["user_id"], ["id"], ondelete="CASCADE")
        op.create_index(f"ix_{table}_user_id", table, ["user_id"], unique=unique)

    for name, (type_, default) in POLICY.items():
        op.add_column("app_settings", sa.Column(name, type_, server_default=default, nullable=False))
    op.add_column("app_settings", sa.Column("secret_key", sa.String(128), nullable=True))
    for name in PREFERENCES:
        op.drop_column("app_settings", name)


def downgrade() -> None:
    for name, (type_, default) in PREFERENCES.items():
        op.add_column("app_settings", sa.Column(name, type_, server_default=default, nullable=False))
    # Preferences become global again: keep the first admin's
    op.execute("""
        UPDATE app_settings SET language = u.language, theme = u.theme, onboarded = u.onboarded
        FROM (SELECT language, theme, onboarded FROM app_user WHERE role = 'admin' ORDER BY id LIMIT 1) AS u
    """)
    op.drop_column("app_settings", "secret_key")
    for name in POLICY:
        op.drop_column("app_settings", name)

    for table in ("application", "profile"):
        op.drop_index(f"ix_{table}_user_id", table_name=table)
        op.drop_constraint(f"{table}_user_id_fkey", table, type_="foreignkey")
        op.drop_column(table, "user_id")
    op.drop_index("ix_app_user_username", table_name="app_user")
    op.drop_table("app_user")
