from fastapi import APIRouter, Depends, status

from app.schemas import UpdateInstall, UpdatesRead, UpdateStatus
from app.services import security, updates

router = APIRouter(prefix="/api/updates", tags=["updates"])


@router.get("", response_model=UpdatesRead, dependencies=[Depends(security.admin_user)])
def get_updates():
    return updates.overview()


@router.get("/status", response_model=UpdateStatus, dependencies=[Depends(security.current_user)])
def get_status():
    """Progress only, polled by every user to show the update screen."""
    return updates.overview()


@router.post("/check", status_code=status.HTTP_202_ACCEPTED, dependencies=[Depends(security.admin_user)])
def check():
    updates.request("check")


@router.post("/install", status_code=status.HTTP_202_ACCEPTED, dependencies=[Depends(security.admin_user)])
def install(payload: UpdateInstall):
    updates.request("install", branch=payload.branch)
