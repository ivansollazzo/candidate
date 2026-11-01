import json
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from app.config import get_settings
from app.schemas import JobCoreExtraction
from app.services import llm


class FakeOllama(BaseHTTPRequestHandler):
    """Streams an answer in two chunks; with "slow" in the prompt it keeps the client waiting."""

    received: list[dict] = []
    disconnected = threading.Event()

    def do_POST(self):
        payload = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        FakeOllama.received.append({"path": self.path, "payload": payload})
        if "slow" in payload["messages"][1]["content"]:
            # Like a long prompt evaluation: nothing is sent until the client goes away
            while self.rfile.read(1):
                pass
            FakeOllama.disconnected.set()
            return
        self.send_response(200)
        self.send_header("Content-Type", "application/x-ndjson")
        self.end_headers()
        for part, done in (('{"title": ', False), ('"Dev"}', True)):
            self.wfile.write(json.dumps({"message": {"content": part}, "done": done}).encode() + b"\n")
            self.wfile.flush()

    def log_message(self, *args):
        pass


@pytest.fixture
def ollama(tmp_path, monkeypatch):
    server = ThreadingHTTPServer(("127.0.0.1", 0), FakeOllama)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    settings = get_settings()
    monkeypatch.setattr(settings, "llm_provider", "auto")
    monkeypatch.setattr(settings, "llm_runtime_file", tmp_path / "llm.json")
    FakeOllama.received.clear()
    FakeOllama.disconnected.clear()
    yield f"http://127.0.0.1:{server.server_port}"
    server.shutdown()


def test_auto_waits_for_runtime_file(ollama, tmp_path):
    assert llm.current_target() is None
    assert llm.check_llm()["starting"] is True

    (tmp_path / "llm.json").write_text(json.dumps({"base_url": ollama, "model": "qwen3:4b", "accelerator": "cuda"}))
    assert llm.generate_structured("s", "u", JobCoreExtraction).title == "Dev"
    [request] = FakeOllama.received
    assert request["path"] == "/api/chat"
    assert request["payload"]["format"]["title"] == "JobCoreExtraction" and request["payload"]["stream"] is True


def test_cancel_stops_the_model(ollama, tmp_path):
    (tmp_path / "llm.json").write_text(json.dumps({"base_url": ollama, "model": "qwen3:4b"}))
    token = llm.CancelToken()
    outcome = {}

    def run():
        llm.cancel_token.set(token)
        try:
            llm.generate_structured("s", "slow", JobCoreExtraction)
        except llm.Cancelled:
            outcome["cancelled"] = True

    worker = threading.Thread(target=run)
    worker.start()
    while not FakeOllama.received:
        time.sleep(0.01)
    token.cancel()
    worker.join(timeout=5)
    assert outcome == {"cancelled": True}
    # The server sees the connection go away, which is what makes Ollama stop generating
    assert FakeOllama.disconnected.wait(timeout=5)
