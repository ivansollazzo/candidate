from datetime import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, Field


class HttpsCertificate(BaseModel):
    """An uploaded certificate, without its key."""

    id: str
    names: list[str]
    issuer: str
    not_before: datetime
    not_after: datetime
    fingerprint: str
    self_signed: bool
    # Names it is served for (a name two certificates hold goes to the newest)
    hosts: list[str]


class HttpsAuthority(BaseModel):
    """Internal mode: the app's own certificate authority, to install on the devices."""

    name: str
    fingerprint: str
    not_after: datetime
    # Expiry of the certificate issued for the hosts, renewed automatically
    leaf_not_after: datetime | None = None


class HttpsRead(BaseModel):
    mode: Literal["off", "internal", "custom"]
    # Hosts of internal mode
    hosts: list[str]
    certificates: list[HttpsCertificate]
    authority: HttpsAuthority | None = None
    # off, active, applying, error, unknown
    state: str
    error: str | None = None
    failed_at: datetime | None = None
    # The page was opened over HTTPS (seen by Caddy)
    secure_request: bool
    port: int


class HttpsUpdate(BaseModel):
    mode: Literal["off", "internal", "custom"]
    hosts: Annotated[list[str], Field(max_length=50)] = []
