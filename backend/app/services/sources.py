"""Job posting text for the LLM, from pasted text, a link or a file."""

from fastapi import HTTPException, UploadFile, status

from app.api.uploads import read_upload
from app.i18n import t
from app.services.documents import UnsupportedDocument, extract_text
from app.services.webpage import FetchError, fetch_job_posting

MIN_CHARS = 20


async def read_job_posting(text: str | None, url: str | None, file: UploadFile | None) -> str | None:
    """Text of the posting given in the request; None when none was given."""
    if file is not None:
        try:
            source = extract_text(file.filename or "", await read_upload(file))
        except UnsupportedDocument as exc:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc)) from exc
    elif url:
        try:
            source = fetch_job_posting(url.strip())
        except FetchError as exc:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc)) from exc
    elif text is not None:
        source = text.strip()
    else:
        return None
    check_length(source)
    return source


def check_length(source: str) -> None:
    if len(source.strip()) < MIN_CHARS:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, t("posting_too_short"))
