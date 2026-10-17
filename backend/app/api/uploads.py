from fastapi import HTTPException, UploadFile, status

from app.config import get_settings
from app.i18n import t


async def read_upload(file: UploadFile) -> bytes:
    limit = get_settings().max_upload_mb * 1024 * 1024
    data = await file.read(limit + 1)
    if len(data) > limit:
        raise HTTPException(status.HTTP_413_CONTENT_TOO_LARGE, t("file_too_large", mb=get_settings().max_upload_mb))
    if not data:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, t("file_empty"))
    return data
