from fastapi import APIRouter, Depends, status
from sqlmodel import Session

from app.features.applications.schemas import ApplicationRead
from app.features.auth.dependencies import current_user
from app.features.auth.models import User
from app.features.reports import service
from app.features.reports.schemas import ApplicationReports, ReportsQueued
from app.shared.database import get_session

router = APIRouter(prefix="/api/applications", tags=["applications"])


@router.post("/reports", response_model=ReportsQueued, status_code=status.HTTP_202_ACCEPTED)
def request_reports(
    payload: ApplicationReports, user: User = Depends(current_user),
    session: Session = Depends(get_session),
):
    """Queue the profile match report of several applications, one job each, in the order given. Applications
    without skills (nothing to compare) and those whose report is already queued are skipped."""
    return service.request_many(session, user, payload.ids)


@router.post("/{application_id}/report", response_model=ApplicationRead, status_code=status.HTTP_202_ACCEPTED)
def request_report(
    application_id: int, user: User = Depends(current_user), session: Session = Depends(get_session),
):
    """Queue the generation (or regeneration) of the profile match report by the local model."""
    return service.request(session, user, application_id)

