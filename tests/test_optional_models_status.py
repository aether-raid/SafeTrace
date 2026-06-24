from fastapi.testclient import TestClient

import src.api.server as server_module
import src.chat_service as chat_service
import src.vlm_reasoner as vlm_reasoner
from src.api.batches import BatchStore
from src.api.jobs import JobStore
from src.api.server import create_app


class FakeTagsResponse:
    def __init__(self, payload):
        self._payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self._payload


def raise_ollama_unreachable(*args, **kwargs):  # noqa: ARG001
    raise RuntimeError("Ollama is not running")


def make_client(tmp_path):
    return TestClient(create_app(JobStore(tmp_path / "jobs"), BatchStore(tmp_path / "batches")))


def test_mobilesam_status_missing_checkpoint(monkeypatch, tmp_path):
    monkeypatch.setattr(server_module.SETTINGS, "mobile_sam_enabled", "auto")
    monkeypatch.setattr(server_module.SETTINGS, "mobile_sam_checkpoint", tmp_path / "missing-mobile-sam.pt")
    monkeypatch.setattr(server_module, "_mobile_sam_runtime_available", lambda: True)

    response = make_client(tmp_path).get("/api/system/status")

    body = response.json()
    assert body["models"]["mobileSam"]["status"] == "missing_checkpoint"
    assert body["models"]["mobileSam"]["details"]["checkpointExists"] is False
    assert body["preflight"]["checks"]["mobileSam"]["status"] == "missing_checkpoint"


def test_mobilesam_status_available_with_temp_checkpoint_and_mocked_runtime(monkeypatch, tmp_path):
    checkpoint = tmp_path / "mobile_sam.pt"
    checkpoint.write_bytes(b"checkpoint placeholder")
    monkeypatch.setattr(server_module.SETTINGS, "mobile_sam_enabled", "auto")
    monkeypatch.setattr(server_module.SETTINGS, "mobile_sam_checkpoint", checkpoint)
    monkeypatch.setattr(server_module, "_mobile_sam_runtime_available", lambda: True)

    response = make_client(tmp_path).get("/api/system/status")

    body = response.json()
    assert body["models"]["mobileSam"]["status"] == "available"
    assert body["models"]["mobileSam"]["details"]["checkpointExists"] is True
    assert body["preflight"]["checks"]["mobileSam"]["status"] == "available"


def test_mobilesam_status_missing_runtime(monkeypatch, tmp_path):
    checkpoint = tmp_path / "mobile_sam.pt"
    checkpoint.write_bytes(b"checkpoint placeholder")
    monkeypatch.setattr(server_module.SETTINGS, "mobile_sam_enabled", "auto")
    monkeypatch.setattr(server_module.SETTINGS, "mobile_sam_checkpoint", checkpoint)
    monkeypatch.setattr(server_module, "_mobile_sam_runtime_available", lambda: False)

    response = make_client(tmp_path).get("/api/system/status")

    body = response.json()
    assert body["models"]["mobileSam"]["status"] == "missing_runtime"
    assert "runtime" in body["models"]["mobileSam"]["message"].lower()


def test_vlm_status_disabled(monkeypatch, tmp_path):
    monkeypatch.setattr(server_module.SETTINGS, "vlm_enabled", "disabled")
    monkeypatch.setattr(vlm_reasoner.SETTINGS, "vlm_enabled", "disabled")

    response = make_client(tmp_path).get("/api/system/status")

    body = response.json()
    assert body["models"]["vlm"]["status"] == "disabled"
    assert body["preflight"]["checks"]["vlm"]["status"] == "disabled"
    assert body["preflight"]["checks"]["visualExplanations"]["status"] == "available"
    assert body["preflight"]["checks"]["visualExplanations"]["details"]["explanationSource"] == "rule_based"
    assert body["runtime"]["visual_explanations"]["fallback"] == "rule_based"


def test_vlm_auto_prefers_existing_local_provider_when_available(monkeypatch, tmp_path):
    model_dir = tmp_path / "vlm_model"
    model_dir.mkdir()
    (model_dir / "config.json").write_text("{}", encoding="utf-8")
    monkeypatch.setattr(server_module.SETTINGS, "vlm_enabled", "auto")
    monkeypatch.setattr(server_module.SETTINGS, "vlm_provider", "auto")
    monkeypatch.setattr(server_module.SETTINGS, "vlm_model_dir", model_dir)
    monkeypatch.setattr(vlm_reasoner, "_transformers_runtime_available", lambda: True)
    monkeypatch.setattr(vlm_reasoner.httpx, "get", raise_ollama_unreachable)

    response = make_client(tmp_path).get("/api/system/status")

    body = response.json()
    assert body["models"]["vlm"]["status"] == "available"
    assert body["models"]["vlm"]["details"]["provider"] == "auto"
    assert body["models"]["vlm"]["details"]["selectedProvider"] == "local"
    assert body["models"]["vlm"]["details"]["availableProviders"] == ["local"]
    assert "local provider" in body["models"]["vlm"]["message"]
    assert body["preflight"]["checks"]["visualExplanations"]["status"] == "available"
    assert body["preflight"]["checks"]["visualExplanations"]["details"]["explanationSource"] == "vlm"
    assert body["runtime"]["visual_explanations"]["enhancedVlmAvailable"] is True


def test_vlm_status_available_when_ollama_is_mocked(monkeypatch, tmp_path):
    def fake_get(url, timeout):  # noqa: ARG001
        return FakeTagsResponse({"models": [{"name": "llava:latest"}]})

    monkeypatch.setattr(server_module.SETTINGS, "vlm_enabled", "auto")
    monkeypatch.setattr(server_module.SETTINGS, "vlm_provider", "ollama")
    monkeypatch.setattr(server_module.SETTINGS, "vlm_ollama_base_url", "http://127.0.0.1:11434")
    monkeypatch.setattr(server_module.SETTINGS, "vlm_model", "llava")
    monkeypatch.setattr(vlm_reasoner.httpx, "get", fake_get)

    response = make_client(tmp_path).get("/api/system/status")

    body = response.json()
    assert body["models"]["vlm"]["status"] == "available"
    assert body["models"]["vlm"]["details"]["provider"] == "ollama"
    assert body["models"]["vlm"]["details"]["selectedProvider"] == "ollama"
    assert body["preflight"]["checks"]["vlm"]["status"] == "available"
    assert body["preflight"]["checks"]["visualExplanations"]["status"] == "available"
    assert body["preflight"]["checks"]["visualExplanations"]["details"]["explanationSource"] == "vlm"


def test_vlm_auto_uses_ollama_when_local_provider_unavailable(monkeypatch, tmp_path):
    def fake_get(url, timeout):  # noqa: ARG001
        return FakeTagsResponse({"models": [{"name": "llava:latest"}]})

    monkeypatch.setattr(server_module.SETTINGS, "vlm_enabled", "auto")
    monkeypatch.setattr(server_module.SETTINGS, "vlm_provider", "auto")
    monkeypatch.setattr(server_module.SETTINGS, "vlm_model_dir", tmp_path / "missing-vlm")
    monkeypatch.setattr(server_module.SETTINGS, "vlm_ollama_base_url", "http://127.0.0.1:11434")
    monkeypatch.setattr(server_module.SETTINGS, "vlm_model", "llava")
    monkeypatch.setattr(vlm_reasoner, "_transformers_runtime_available", lambda: True)
    monkeypatch.setattr(vlm_reasoner.httpx, "get", fake_get)

    response = make_client(tmp_path).get("/api/system/status")

    body = response.json()
    assert body["models"]["vlm"]["status"] == "available"
    assert body["models"]["vlm"]["details"]["provider"] == "auto"
    assert body["models"]["vlm"]["details"]["selectedProvider"] == "ollama"
    assert body["models"]["vlm"]["details"]["availableProviders"] == ["ollama"]


def test_vlm_auto_reports_rule_based_fallback_when_no_provider_available(monkeypatch, tmp_path):
    monkeypatch.setattr(server_module.SETTINGS, "vlm_enabled", "auto")
    monkeypatch.setattr(server_module.SETTINGS, "vlm_provider", "auto")
    monkeypatch.setattr(server_module.SETTINGS, "vlm_model_dir", tmp_path / "missing-vlm")
    monkeypatch.setattr(server_module.SETTINGS, "vlm_ollama_base_url", "http://127.0.0.1:11434")
    monkeypatch.setattr(vlm_reasoner, "_transformers_runtime_available", lambda: True)
    monkeypatch.setattr(vlm_reasoner.httpx, "get", raise_ollama_unreachable)

    response = make_client(tmp_path).get("/api/system/status")

    body = response.json()
    assert body["models"]["vlm"]["status"] == "unavailable"
    assert body["models"]["vlm"]["details"]["provider"] == "auto"
    assert body["models"]["vlm"]["details"]["selectedProvider"] == "rule_based"
    assert body["models"]["vlm"]["details"]["availableProviders"] == []
    assert "rule-based explanations" in body["models"]["vlm"]["message"]
    assert body["preflight"]["checks"]["visualExplanations"]["status"] == "available"
    assert body["preflight"]["checks"]["visualExplanations"]["details"]["fallback"] == "rule_based"
    assert body["preflight"]["checks"]["visualExplanations"]["details"]["explanationSource"] == "rule_based"
    assert body["runtime"]["visual_explanations"]["status"] == "available"
    assert body["runtime"]["visual_explanations"]["fallback"] == "rule_based"
    assert body["runtime"]["visual_explanations"]["enhancedVlmAvailable"] is False


def test_chat_and_vlm_statuses_are_independent(monkeypatch, tmp_path):
    def fake_get(url, timeout):  # noqa: ARG001
        return FakeTagsResponse({"models": [{"name": "llava:latest"}]})

    monkeypatch.setattr(server_module.SETTINGS, "vlm_enabled", "auto")
    monkeypatch.setattr(server_module.SETTINGS, "vlm_provider", "ollama")
    monkeypatch.setattr(server_module.SETTINGS, "vlm_ollama_base_url", "http://127.0.0.1:11434")
    monkeypatch.setattr(server_module.SETTINGS, "vlm_model", "llava")
    monkeypatch.setattr(vlm_reasoner.httpx, "get", fake_get)
    monkeypatch.setattr(chat_service.SETTINGS, "chat_provider", "packaged_llamacpp")
    monkeypatch.setattr(chat_service.SETTINGS, "chat_model_path", tmp_path / "missing-chat.gguf")

    response = make_client(tmp_path).get("/api/system/status")

    body = response.json()
    assert body["models"]["vlm"]["status"] == "available"
    assert body["runtime"]["chat"]["state"] == "missing_model"
    assert body["preflight"]["checks"]["assistantModel"]["status"] == "missing"
