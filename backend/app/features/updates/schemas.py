
from pydantic import BaseModel


class UpdateStatus(BaseModel):
    # unavailable (no updater), idle, checking, updating
    status: str
    # backup, download, restart (services being replaced), verify (waiting for the new backend)
    step: str | None = None
    # Estimated completion of the running update, 0-100
    progress: int = 0
    version: str
    build: str


class UpdateBranch(BaseModel):
    name: str
    commit: str = ""
    version: str
    build: str
    # The images of its commit are on GHCR: only then it can be installed
    published: bool
    newer: bool


class UpdateResult(BaseModel):
    # ok, failed
    result: str
    # branch, image, backup, download, start
    error: str = ""
    detail: str = ""
    finished_at: str


class CheckError(BaseModel):
    # The repository couldn't be reached; cleared by the next successful check
    detail: str = ""
    failed_at: str


class UpdatesRead(UpdateStatus):
    selected_branch: str
    checked_at: str | None = None
    branches: list[UpdateBranch]
    update_available: bool
    last: UpdateResult | None = None
    check_error: CheckError | None = None
    # AI jobs waiting or running (all users): an update can be installed only when there are none
    active_jobs: int = 0
