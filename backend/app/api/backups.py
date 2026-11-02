from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from sqlmodel import Session

from app.db import get_session
from app.i18n import t
from app.schemas import BackupCreate, BackupsRead, BackupSettings
from app.services import backups, jobs, security, updates

router = APIRouter(prefix="/api/backups", tags=["backups"], dependencies=[Depends(security.admin_user)])


@router.get("", response_model=BackupsRead)
def get_backups():
    """Backups, newest first, with the schedule and the cleanup rules."""
    state = backups.call("GET", "status").json()
    return {**state, "backups": backups.call("GET", "backups").json(), "last_restore": backups.last_restore()}


@router.put("/settings", response_model=BackupSettings)
def update_backup_settings(payload: BackupSettings):
    return backups.call("PUT", "settings", json=payload.model_dump()).json()


@router.post("", status_code=status.HTTP_201_CREATED)
def create_backup(payload: BackupCreate):
    """A manual backup; answers once it is written."""
    return backups.call("POST", "backups", json={"kind": "manual", "note": payload.note}).json()


@router.delete("/{name}", status_code=status.HTTP_204_NO_CONTENT)
def delete_backup(name: str):
    backups.call("DELETE", f"backups/{name}")


@router.get("/{name}/file")
def download_backup(name: str):
    """The archive, streamed from the backup service."""
    client = backups.httpx.Client(timeout=backups.TIMEOUT)
    try:
        response = client.send(client.build_request("GET", backups._url(f"backups/{name}/file")), stream=True)
    except backups.httpx.HTTPError as exc:
        client.close()
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, t("backup_unavailable")) from exc
    if response.status_code != 200:
        response.close()
        client.close()
        raise HTTPException(status.HTTP_404_NOT_FOUND, t("backup_not_found"))

    def chunks():
        try:
            yield from response.iter_bytes(1 << 20)
        finally:
            response.close()
            client.close()

    headers = {"Content-Disposition": f'attachment; filename="{name}"'}
    if "content-length" in response.headers:
        headers["Content-Length"] = response.headers["content-length"]
    return StreamingResponse(chunks(), media_type="application/gzip", headers=headers)


@router.post("/{name}/restore", status_code=status.HTTP_202_ACCEPTED)
def restore_backup(name: str, session: Session = Depends(get_session)):
    """Put database and files back as in the backup. The current state is saved first; meanwhile the app is
    in maintenance."""
    if updates.installing():
        raise HTTPException(status.HTTP_409_CONFLICT, t("restore_updating"))
    if jobs.count_active(session):
        raise HTTPException(status.HTTP_409_CONFLICT, t("restore_jobs_active"))
    if backups.restoring():
        raise HTTPException(status.HTTP_409_CONFLICT, t("backup_busy"))
    backup = next((item for item in backups.call("GET", "backups").json() if item["name"] == name), None)
    if backup is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, t("backup_not_found"))
    backups.check_restorable(backup)
    session.close()
    backups.start_restore(name)
