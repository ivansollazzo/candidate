from fastapi import APIRouter, Depends, status
from sqlmodel import Session

from app.db import get_session
from app.schemas import UpdatesRead, UpdateStatus
from app.services import app_settings, security, updates

router = APIRouter(prefix="/api/updates", tags=["updates"])


def selected_branch(session: Session = Depends(get_session)) -> str | None:
    return app_settings.load(session).update_branch


@router.get("", response_model=UpdatesRead, dependencies=[Depends(security.admin_user)])
def get_updates(selected: str | None = Depends(selected_branch)):
    return updates.overview(selected)


@router.get("/status", response_model=UpdateStatus, dependencies=[Depends(security.current_user)])
def get_status():
    """Progress only, polled by every user to show the update screen."""
    return updates.overview(None)


@router.post("/check", status_code=status.HTTP_202_ACCEPTED, dependencies=[Depends(security.admin_user)])
def check():
    updates.request("check")


@router.post("/install", status_code=status.HTTP_202_ACCEPTED, dependencies=[Depends(security.admin_user)])
def install(selected: str | None = Depends(selected_branch)):
    """Install the newer release of the selected branch."""
    updates.request("install", selected)
