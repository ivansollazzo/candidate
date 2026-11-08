"""Minimal Ollama client with JSON output constrained to a Pydantic schema; a running call can be cancelled."""

import http.client
import json
import logging
import socket
import threading
from contextvars import ContextVar
from dataclasses import dataclass
from typing import TypeVar
from urllib.parse import urlsplit

import httpx
from pydantic import BaseModel, ValidationError

from app.core.config import get_settings
from app.core.i18n import t

log = logging.getLogger(__name__)

T = TypeVar("T", bound=BaseModel)


class LLMError(RuntimeError):
    pass


class Cancelled(Exception):
    """The job using the model was cancelled."""


class CancelToken:
    """Stops the model mid-answer: shutting the connection down makes Ollama stop generating."""

    def __init__(self) -> None:
        self.cancelled = False
        self._sock: socket.socket | None = None
        self._lock = threading.Lock()

    def attach(self, sock: socket.socket | None) -> None:
        with self._lock:
            if self.cancelled:
                raise Cancelled
            self._sock = sock

    def detach(self) -> None:
        with self._lock:
            self._sock = None

    def cancel(self) -> None:
        with self._lock:
            self.cancelled = True
            if self._sock is not None:
                try:
                    # Wakes up the read blocked in the worker thread
                    self._sock.shutdown(socket.SHUT_RDWR)
                except OSError:
                    pass


# Token of the job running in this thread, set by the job queue
cancel_token: ContextVar[CancelToken | None] = ContextVar("cancel_token", default=None)


@dataclass
class LLMTarget:
    base_url: str
    model: str
    accelerator: str | None = None


def current_target() -> LLMTarget | None:
    """Ollama server to use; None if the docker compose llm service hasn't started it yet."""
    settings = get_settings()
    if settings.llm_provider == "ollama":
        return LLMTarget(settings.llm_base_url, settings.llm_model)
    try:
        data = json.loads(settings.llm_runtime_file.read_text())
        return LLMTarget(data["base_url"], data["model"], data.get("accelerator"))
    except (OSError, ValueError, KeyError):
        return None


def generate_structured(system: str, user: str, schema: type[T]) -> T:
    """Ask the model for a response matching `schema` (Ollama structured outputs)."""
    settings = get_settings()
    target = current_target()
    if target is None:
        raise LLMError(t("llm_starting"))
    payload = {
        "model": target.model,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        "format": schema.model_json_schema(),
        # Streamed, so a cancelled job can drop the connection and stop the model
        "stream": True,
        # Disable Qwen 3 "thinking" mode for faster responses
        "think": False,
        "options": {"temperature": 0, "num_ctx": settings.llm_num_ctx},
    }
    content = "".join(_chat(target.base_url, payload, settings.llm_timeout_seconds))
    try:
        return schema.model_validate(json.loads(content))
    except (json.JSONDecodeError, ValidationError) as exc:
        log.warning("Invalid LLM response: %s", content[:500])
        raise LLMError(t("llm_invalid", error=exc)) from exc


def _chat(base_url: str, payload: dict, timeout: float) -> list[str]:
    """POST /api/chat and collect the streamed answer, giving up as soon as the job is cancelled."""
    url = urlsplit(base_url)
    connection_class = http.client.HTTPSConnection if url.scheme == "https" else http.client.HTTPConnection
    conn = connection_class(url.hostname or "localhost", url.port, timeout=timeout)
    token = cancel_token.get()
    parts: list[str] = []
    try:
        conn.connect()
        if token is not None:
            token.attach(conn.sock)
        conn.request("POST", url.path.rstrip("/") + "/api/chat", body=json.dumps(payload),
                     headers={"Content-Type": "application/json"})
        response = conn.getresponse()
        if response.status != 200:
            text = response.read().decode(errors="replace")
            raise LLMError(t("llm_http_error", code=response.status, text=text[:300]))
        for line in response:
            if not line.strip():
                continue
            chunk = json.loads(line)
            if chunk.get("error"):
                raise LLMError(t("llm_http_error", code=response.status, text=str(chunk["error"])[:300]))
            parts.append(chunk.get("message", {}).get("content", ""))
            if chunk.get("done"):
                break
    except (OSError, http.client.HTTPException, ValueError) as exc:
        if token is not None and token.cancelled:
            raise Cancelled from exc
        raise LLMError(t("llm_unreachable", url=base_url, error=exc)) from exc
    finally:
        if token is not None:
            token.detach()
        conn.close()
    if token is not None and token.cancelled:
        raise Cancelled
    return parts


def hardware_support() -> dict | None:
    """Hardware stacks detected by the llm service: available, unavailable, failed (detected but not used by Ollama)."""
    try:
        return json.loads((get_settings().llm_runtime_file.parent / "hardware.json").read_text())
    except (OSError, ValueError):
        return None  # backend running outside Docker, or detection not finished yet


def check_llm() -> dict:
    target = current_target()
    if target is None:
        return {"model": None, "accelerator": None, "starting": True, "reachable": False, "model_available": False}
    info = {"model": target.model, "accelerator": target.accelerator, "starting": False}
    try:
        response = httpx.get(f"{target.base_url}/api/tags", timeout=5)
        response.raise_for_status()
    except httpx.HTTPError as exc:
        return {**info, "reachable": False, "model_available": False, "error": str(exc)}
    names = {m.get("name") for m in response.json().get("models", [])}
    available = target.model in names or f"{target.model}:latest" in names
    return {**info, "reachable": True, "model_available": available}
