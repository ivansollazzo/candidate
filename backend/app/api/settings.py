from fastapi import APIRouter, Depends
from sqlmodel import Session

from app.db import get_session
from app.schemas import SettingsRead, SettingsUpdate
from app.services import app_settings, security

router = APIRouter(prefix="/api/settings", tags=["settings"])


@router.get("", response_model=SettingsRead, dependencies=[Depends(security.current_user)])
def get_settings(session: Session = Depends(get_session)):
    return app_settings.load(session)


@router.patch("", response_model=SettingsRead, dependencies=[Depends(security.admin_user)])
def update_settings(payload: SettingsUpdate, session: Session = Depends(get_session)):
    settings = app_settings.load(session)
    for field, value in payload.model_dump(exclude_unset=True, exclude_none=True).items():
        setattr(settings, field, value)
    session.add(settings)
    session.commit()
    session.refresh(settings)
    app_settings.publish(settings)
    return settings
