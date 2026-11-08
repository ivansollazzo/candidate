"""Files attached to an application, kept in the owner's folder."""

import shutil
import uuid
from pathlib import Path

from fastapi import UploadFile

from app.core.config import get_settings
from app.features.applications.models import Application, ApplicationAttachment
from app.shared.storage import read_upload


def attachments_dir(app: Application) -> Path:
    """Folder holding the application's attachments, inside the owner's file directory."""
    return get_settings().upload_dir / f"user_{app.user_id}" / "applications" / str(app.id)


def attachment_path(app: Application, attachment: ApplicationAttachment) -> Path:
    return attachments_dir(app) / attachment.stored_name


async def save_attachments(app: Application, files: list[UploadFile]) -> list[ApplicationAttachment]:
    """Write the files to disk; every file is read (and size-checked) before any is written."""
    contents = [(file, await read_upload(file)) for file in files]
    folder = attachments_dir(app)
    folder.mkdir(parents=True, exist_ok=True)
    attachments = []
    for file, data in contents:
        # Random name on disk: the original one is only metadata
        stored_name = uuid.uuid4().hex + Path(file.filename or "").suffix.lower()[:10]
        (folder / stored_name).write_bytes(data)
        attachments.append(ApplicationAttachment(
            application_id=app.id,
            filename=Path(file.filename or "file").name[:255] or "file",
            stored_name=stored_name,
            content_type=(file.content_type or None) and file.content_type[:255],
            size=len(data),
        ))
    return attachments


def remove_attachments(folders: list[Path]) -> None:
    """Delete the attachment folders of deleted applications."""
    for folder in folders:
        shutil.rmtree(folder, ignore_errors=True)
