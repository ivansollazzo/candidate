"""User-facing messages, picked by UI language (Accept-Language header); one module per language in locales/."""

from contextvars import ContextVar
from importlib import import_module

LANGUAGES = ("it", "en", "es", "fr", "de")
DEFAULT_LANGUAGE = "it"

current_language: ContextVar[str] = ContextVar("language", default=DEFAULT_LANGUAGE)

MESSAGES: dict[str, dict[str, str]] = {
    code: import_module(f"app.core.locales.{code}").MESSAGES for code in LANGUAGES
}


def t(key: str, **values) -> str:
    return MESSAGES[current_language.get()][key].format(**values)


def parse_language(header: str) -> str:
    """First supported language in the Accept-Language header (e.g. "en-GB,en;q=0.9")."""
    for part in header.split(","):
        code = part.split(";")[0].strip()[:2].lower()
        if code in LANGUAGES:
            return code
    return DEFAULT_LANGUAGE


class LanguageMiddleware:
    """Set the request language; also applies to background tasks it starts."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] == "http":
            headers = dict(scope["headers"])
            current_language.set(parse_language(headers.get(b"accept-language", b"").decode("latin-1")))
        await self.app(scope, receive, send)
