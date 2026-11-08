from datetime import datetime

from pydantic import BaseModel, ConfigDict


class JobRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    kind: str  # application | profile | report
    status: str  # pending | running | done | failed
    application_id: int | None
    application_title: str | None = None
    new_application: bool
    then_report: bool
    # Place in the queue shared by all users (1 = next), for waiting jobs
    position: int | None = None
    # Values found for fields already filled, waiting for the user to apply them
    proposal: dict | None
    error: str | None
    created_at: datetime
    finished_at: datetime | None
