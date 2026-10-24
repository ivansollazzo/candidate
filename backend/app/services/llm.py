"""Minimal Ollama client with JSON output constrained to a Pydantic schema."""

import copy
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


# Temperature of each attempt: a small model now and then answers with something unusable, and the same
# request at temperature 0 would get the same answer again
TEMPERATURES = (0, 0.4)


def strict_schema(schema: dict) -> dict:
    """JSON schema with every property required (still nullable where the model allows it). With optional
    properties the output grammar accepts {}, and small models take that shortcut."""
    def visit(node):
        if isinstance(node, dict):
            if node.get("type") == "object" and "properties" in node:
                node["required"] = list(node["properties"])
            for value in node.values():
                visit(value)
        elif isinstance(node, list):
            for value in node:
                visit(value)

    schema = copy.deepcopy(schema)
    visit(schema)
    return schema


def first_object(content: str) -> dict:
    """The first JSON object in the response: models sometimes add text or special tokens after it
    (e.g. '{...}<|tool_response>') or wrap it in a ```json block."""
    start = content.find("{")
    if start < 0:
        raise json.JSONDecodeError("no JSON object", content, 0)
    value, _ = json.JSONDecoder().raw_decode(content, start)
    return value


def generate_structured(system: str, user: str, schema: type[T]) -> T:
    """Ask the model for a response matching `schema` (Ollama structured outputs)."""
    error: Exception | None = None
    for temperature in TEMPERATURES:
        content = _chat(system, user, strict_schema(schema.model_json_schema()), temperature)
        try:
            data = first_object(content)
            if not data:
                raise ValueError("empty object")
            return schema.model_validate(data)
        except (ValueError, ValidationError) as exc:  # JSONDecodeError is a ValueError
            log.warning("Invalid LLM response: %s", content[:500])
            error = exc
    raise LLMError(t("llm_invalid", error=error))


def _chat(system: str, user: str, schema: dict, temperature: float) -> str:
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
        "format": schema,
        "stream": False,
        # Reasoning off: extraction follows strict prompts and doesn't need it, and it would be much slower
        "think": False,
        "options": {"temperature": temperature, "num_ctx": settings.llm_num_ctx},
    }
    try:
        response = httpx.post(f"{target.base_url}/api/chat", json=payload, timeout=settings.llm_timeout_seconds)
        response.raise_for_status()
    except httpx.HTTPStatusError as exc:
        raise LLMError(t("llm_http_error", code=exc.response.status_code, text=exc.response.text[:300])) from exc
    except httpx.HTTPError as exc:
        raise LLMError(t("llm_unreachable", url=target.base_url, error=exc)) from exc

    return response.json().get("message", {}).get("content", "")


def hardware_support() -> dict | None:
    """Hardware stacks detected by the llm service: available, unavailable, failed (detected but not used by Ollama)."""
    try:
        return json.loads((get_settings().llm_runtime_file.parent / "hardware.json").read_text())
    except (OSError, ValueError):
        return None  # backend running outside Docker, or detection not finished yet


def download_progress() -> dict | None:
    """Model the llm service is downloading, with the percentage done."""
    try:
        return json.loads((get_settings().llm_runtime_file.parent / "pull.json").read_text())
    except (OSError, ValueError):
        return None


def check_llm() -> dict:
    target = current_target()
    if target is None:
        return {"model": None, "accelerator": None, "starting": True, "reachable": False, "model_available": False,
                "download": download_progress()}
    info = {"model": target.model, "accelerator": target.accelerator, "starting": False}
    try:
        response = httpx.get(f"{target.base_url}/api/tags", timeout=5)
        response.raise_for_status()
    except httpx.HTTPError as exc:
        return {**info, "reachable": False, "model_available": False, "error": str(exc)}
    names = {m.get("name") for m in response.json().get("models", [])}
    available = target.model in names or f"{target.model}:latest" in names
    return {**info, "reachable": True, "model_available": available}
