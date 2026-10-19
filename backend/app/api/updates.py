from fastapi import APIRouter, Depends, status
from sqlmodel import Session

from app.db import get_session
from app.schemas import UpdatesRead, UpdateStatus
from app.services import app_settings, security, updates

router = APIRouter(prefix="/api/updates", tags=["updates"])


def followed_branch(session: Session = Depends(get_session)) -> str | None:
    return app_settings.load(session).update_branch


@router.get("", response_model=UpdatesRead, dependencies=[Depends(security.admin_user)])
def get_updates(followed: str | None = Depends(followed_branch)):
    return updates.overview(followed)


@router.get("/status", response_model=UpdateStatus, dependencies=[Depends(security.current_user)])
def get_status(followed: str | None = Depends(followed_branch)):
    """Progress only, polled by every user to show the update screen."""
    return updates.overview(followed)


@router.post("/check", status_code=status.HTTP_202_ACCEPTED, dependencies=[Depends(security.admin_user)])
def check():
    updates.request("check")


@router.post("/install", status_code=status.HTTP_202_ACCEPTED, dependencies=[Depends(security.admin_user)])
def install(followed: str | None = Depends(followed_branch)):
    """Install the newer release of the followed branch."""
    updates.request("install", followed)
