from fastapi import APIRouter, Depends, HTTPException, status
from sqlmodel import Session

from app.core.i18n import t
from app.schemas import UpdatesRead, UpdateStatus
from app.services import app_settings, jobs, security, updates
from app.shared import maintenance
from app.shared.database import get_session

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


@router.post("/checks", status_code=status.HTTP_202_ACCEPTED, dependencies=[Depends(security.admin_user)])
def check():
    updates.request("check")


@router.post("/installations", status_code=status.HTTP_202_ACCEPTED, dependencies=[Depends(security.admin_user)])
def install(selected: str | None = Depends(selected_branch), session: Session = Depends(get_session)):
    """Install the newer release of the selected branch, once no AI job of any user is waiting or running."""
    if jobs.count_active(session):
        raise HTTPException(status.HTTP_409_CONFLICT, t("update_jobs_active"))
    if maintenance.restoring():
        raise HTTPException(status.HTTP_409_CONFLICT, t("restoring"))
    updates.request("install", selected)
