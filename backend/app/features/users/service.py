"""Account files: profile photo and the user's folder."""

import io
import shutil
from pathlib import Path

from fastapi import HTTPException, status
from fastapi.responses import FileResponse
from PIL import Image, UnidentifiedImageError

from app.core.config import get_settings
from app.core.i18n import t
from app.features.auth.models import User, UserRole
from app.shared.storage import user_dir

AVATAR_SIZE = 256

# Larger images are rejected ("decompression bomb" protection)
Image.MAX_IMAGE_PIXELS = 40_000_000


def save_avatar(user: User, data: bytes) -> None:
    """Resize the photo and save it as WebP; re-encoding strips metadata and any embedded payload."""
    try:
        with Image.open(io.BytesIO(data)) as image:
            image.load()
            image = image.convert("RGBA") if image.mode in ("RGBA", "LA", "P") else image.convert("RGB")
            # Centered square crop
            side = min(image.size)
            left, top = (image.width - side) // 2, (image.height - side) // 2
            image = image.crop((left, top, left + side, top + side)).resize((AVATAR_SIZE, AVATAR_SIZE))
            path = user_dir(user.id) / "avatar.webp"
            image.save(path, "WEBP", quality=85)
    except (UnidentifiedImageError, Image.DecompressionBombError, OSError) as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, t("invalid_image")) from exc
    user.avatar_path = str(path)


def remove_avatar(user: User) -> None:
    if user.avatar_path:
        Path(user.avatar_path).unlink(missing_ok=True)
    user.avatar_path = None


def remove_files(user_id: int) -> None:
    shutil.rmtree(get_settings().upload_dir / f"user_{user_id}", ignore_errors=True)


def avatar_response(target: User | None, viewer: User) -> FileResponse:
    if target is None or (target.id != viewer.id and viewer.role != UserRole.ADMIN):
        raise HTTPException(status.HTTP_404_NOT_FOUND, t("user_not_found"))
    if not target.avatar_path or not Path(target.avatar_path).exists():
        raise HTTPException(status.HTTP_404_NOT_FOUND, t("no_avatar"))
    return FileResponse(target.avatar_path, media_type="image/webp", headers={"Cache-Control": "private, no-cache"})
