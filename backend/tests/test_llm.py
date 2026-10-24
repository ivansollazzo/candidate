import json

import httpx

from app.config import get_settings
from app.schemas import JobCoreExtraction
from app.services import llm


def test_auto_waits_for_runtime_file(tmp_path, monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings, "llm_provider", "auto")
    monkeypatch.setattr(settings, "llm_runtime_file", tmp_path / "llm.json")
    assert llm.current_target() is None
    assert llm.check_llm()["starting"] is True

    (tmp_path / "llm.json").write_text(json.dumps(
        {"base_url": "http://ollama:11434", "model": "gemma4:e2b", "accelerator": "cuda"}))
    captured = {}

    def fake_post(url, json, timeout):
        captured.update(url=url, payload=json)
        body = {"message": {"content": '{"title": "Dev"}'}}
        return httpx.Response(200, json=body, request=httpx.Request("POST", url))

    monkeypatch.setattr(llm.httpx, "post", fake_post)
    assert llm.generate_structured("s", "u", JobCoreExtraction).title == "Dev"
    assert captured["url"] == "http://ollama:11434/api/chat"
    assert captured["payload"]["format"]["title"] == "JobCoreExtraction"
    # Every field must be written, so an empty object doesn't satisfy the output grammar
    assert set(captured["payload"]["format"]["required"]) == set(JobCoreExtraction.model_fields)


def test_empty_or_trailing_output_retried(tmp_path, monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings, "llm_provider", "ollama")
    answers = iter(["{}<|tool_response>", '```json\n{"title": "Dev"}\n```<|tool_response>'])
    temperatures = []

    def fake_post(url, json, timeout):
        temperatures.append(json["options"]["temperature"])
        body = {"message": {"content": next(answers)}}
        return httpx.Response(200, json=body, request=httpx.Request("POST", url))

    monkeypatch.setattr(llm.httpx, "post", fake_post)
    assert llm.generate_structured("s", "u", JobCoreExtraction).title == "Dev"
    assert temperatures == [0, 0.4]


def test_strict_schema_requires_nested_fields():
    from app.schemas import JobRequirementsExtraction

    schema = llm.strict_schema(JobRequirementsExtraction.model_json_schema())
    assert set(schema["required"]) == {"responsibilities", "requirements", "nice_to_have", "skills"}
    assert schema["$defs"]["ExtractedSkill"]["required"] == ["name", "importance"]


def test_download_progress_while_starting(tmp_path, monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings, "llm_provider", "auto")
    monkeypatch.setattr(settings, "llm_runtime_file", tmp_path / "llm.json")
    assert llm.check_llm()["download"] is None
    (tmp_path / "pull.json").write_text(json.dumps({"model": "gemma4:e4b", "progress": 42}))
    assert llm.check_llm()["download"] == {"model": "gemma4:e4b", "progress": 42}


def test_clean_posting_drops_repeated_lines_and_blank_runs():
    from app.services.extraction import clean_posting

    text = "Menu\n\n\n  Backend   Developer \nMilano\nMenu\n\n\n\nRAL 35k\n"
    assert clean_posting(text) == "Menu\n\nBackend Developer\nMilano\n\nRAL 35k"
