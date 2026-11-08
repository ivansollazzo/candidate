"""Files: uploads read with the size limit, and each user's folder."""

from pathlib import Path

from fastapi import HTTPException, UploadFile, status

from app.core.config import get_settings
from app.core.i18n import t


async def read_upload(file: UploadFile) -> bytes:
    limit = get_settings().max_upload_mb * 1024 * 1024
    data = await file.read(limit + 1)
    if len(data) > limit:
        raise HTTPException(status.HTTP_413_CONTENT_TOO_LARGE, t("file_too_large", mb=get_settings().max_upload_mb))
    if not data:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, t("file_empty"))
    return data


def user_dir(user_id: int) -> Path:
    """User's file directory (CV, profile photo)."""
    folder = get_settings().upload_dir / f"user_{user_id}"
    folder.mkdir(parents=True, exist_ok=True)
    return folder
