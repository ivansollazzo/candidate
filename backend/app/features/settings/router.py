from fastapi import APIRouter, Depends
from sqlmodel import Session

from app.features.auth.dependencies import admin_user, current_user
from app.features.settings import service
from app.features.settings.schemas import SettingsRead, SettingsUpdate
from app.shared.database import get_session, save

router = APIRouter(prefix="/api/settings", tags=["settings"])


@router.get("", response_model=SettingsRead, dependencies=[Depends(current_user)])
def get_settings(session: Session = Depends(get_session)):
    return service.load(session)


@router.patch("", response_model=SettingsRead, dependencies=[Depends(admin_user)])
def update_settings(payload: SettingsUpdate, session: Session = Depends(get_session)):
    settings = service.load(session)
    # Reports exist only with AI on; jobs waiting for the model are dropped (callbacks registered in main.wire)
    service.apply_changes(session, settings, payload.model_dump(exclude_unset=True, exclude_none=True))
    save(session, settings)
    service.publish(settings)
    return settings
