"""Minimal Ollama client with JSON output constrained to a Pydantic schema."""

import json
import logging
from dataclasses import dataclass
from typing import TypeVar

import httpx
from pydantic import BaseModel, ValidationError

from app.config import get_settings
from app.i18n import t

log = logging.getLogger(__name__)

T = TypeVar("T", bound=BaseModel)


class LLMError(RuntimeError):
    pass


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
        "stream": False,
        # Disable Qwen 3 "thinking" mode for faster responses
        "think": False,
        "options": {"temperature": 0, "num_ctx": settings.llm_num_ctx},
    }
    try:
        response = httpx.post(f"{target.base_url}/api/chat", json=payload, timeout=settings.llm_timeout_seconds)
        response.raise_for_status()
    except httpx.HTTPStatusError as exc:
        raise LLMError(t("llm_http_error", code=exc.response.status_code, text=exc.response.text[:300])) from exc
    except httpx.HTTPError as exc:
        raise LLMError(t("llm_unreachable", url=target.base_url, error=exc)) from exc

    content = response.json().get("message", {}).get("content", "")
    try:
        return schema.model_validate(json.loads(content))
    except (json.JSONDecodeError, ValidationError) as exc:
        log.warning("Risposta LLM non valida: %s", content[:500])
        raise LLMError(t("llm_invalid", error=exc)) from exc


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
