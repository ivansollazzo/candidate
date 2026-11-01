from fastapi import APIRouter, Depends, HTTPException, status
from sqlmodel import Session

from app.db import get_session
from app.i18n import t
from app.schemas import UpdatesRead, UpdateStatus
from app.services import app_settings, jobs, security, updates

router = APIRouter(prefix="/api/updates", tags=["updates"])


def selected_branch(session: Session = Depends(get_session)) -> str | None:
    return app_settings.load(session).update_branch


@router.get("", response_model=UpdatesRead, dependencies=[Depends(security.admin_user)])
def get_updates(selected: str | None = Depends(selected_branch), session: Session = Depends(get_session)):
    return {**updates.overview(selected), "active_jobs": jobs.count_active(session)}


@router.get("/status", response_model=UpdateStatus, dependencies=[Depends(security.current_user)])
def get_status():
    """Progress only, polled by every user to show the update screen."""
    return updates.overview(None)


@router.post("/check", status_code=status.HTTP_202_ACCEPTED, dependencies=[Depends(security.admin_user)])
def check():
    updates.request("check")


@router.post("/install", status_code=status.HTTP_202_ACCEPTED, dependencies=[Depends(security.admin_user)])
def install(selected: str | None = Depends(selected_branch), session: Session = Depends(get_session)):
    """Install the newer release of the selected branch, once no AI job of any user is waiting or running."""
    if jobs.count_active(session):
        raise HTTPException(status.HTTP_409_CONFLICT, t("update_jobs_active"))
    updates.request("install", selected)


@router.post("/cancel", status_code=status.HTTP_204_NO_CONTENT, dependencies=[Depends(security.admin_user)])
def cancel():
    """Cancel a running install until the services are being replaced."""
    updates.cancel()
