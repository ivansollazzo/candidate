from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class SettingsRead(BaseModel):
    """System settings; user preferences (language, theme) live on UserRead."""

    model_config = ConfigDict(from_attributes=True)

    llm_enabled: bool
    llm_accelerator: str
    update_branch: str | None
    update_check_hours: int
    password_min_length: int
    password_require_uppercase: bool
    password_require_digit: bool
    password_require_symbol: bool
    session_hours: int
    max_login_attempts: int
    lockout_minutes: int


class SettingsUpdate(BaseModel):
    llm_enabled: bool | None = None
    llm_accelerator: Literal["auto", "cuda", "rocm", "vulkan", "cpu"] | None = None
    # Branch to update from; empty string: the default branch ("stable")
    update_branch: str | None = Field(default=None, max_length=200)
    update_check_hours: Literal[0, 1, 6, 12, 24, 168] | None = None
    password_min_length: int | None = Field(default=None, ge=8, le=128)
    password_require_uppercase: bool | None = None
    password_require_digit: bool | None = None
    password_require_symbol: bool | None = None
    session_hours: int | None = Field(default=None, ge=1, le=720)
    max_login_attempts: int | None = Field(default=None, ge=0, le=100)
    lockout_minutes: int | None = Field(default=None, ge=1, le=1440)
