from typing import Literal

from pydantic import BaseModel, Field


class BackupSettings(BaseModel):
    # off, daily, weekly; the hour (and the weekday, Monday 0) are in the time zone of the browser that saved them
    frequency: Literal["off", "daily", "weekly"] = "daily"
    hour: int = Field(default=3, ge=0, le=23)
    weekday: int = Field(default=0, ge=0, le=6)
    timezone: str = Field(default="UTC", max_length=64)
    # Automatic backups kept, and the age after which they go (0 = no limit); other backups are never removed
    keep: int = Field(default=7, ge=1, le=365)
    max_age_days: int = Field(default=0, ge=0, le=3650)


class BackupCreate(BaseModel):
    note: str = Field(default="", max_length=200)


class Backup(BaseModel):
    name: str
    # auto, manual, update (before an update), restore (before a restore)
    kind: str
    note: str = ""
    created_at: str | None = None
    version: str = ""
    build: str = ""
    revision: str | None = None
    size: int
    broken: bool = False


class BackupResult(BaseModel):
    result: str
    detail: str = ""
    at: str | None = None


class RestoreResult(BaseModel):
    name: str
    result: str
    detail: str = ""
    finished_at: str


class BackupsRead(BaseModel):
    settings: BackupSettings
    backups: list[Backup]
    # backup or restore, while one runs
    running: dict | None = None
    last_auto: BackupResult | None = None
    last_restore: RestoreResult | None = None
