import httpx
import numpy as np

import src.vlm_reasoner as vlm_reasoner
from src.schemas import Violation
from src.vlm_reasoner import VLM_PROMPT, VlmReasoner, is_local_vlm_base_url


class FakeGenerateResponse:
    def __init__(self, payload):
        self._payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self._payload


def make_violation():
    return Violation(
        name="helmet_missing",
        description="Worker head detected without overlapping helmet.",
        severity="high",
        confidence=0.9,
    )


def test_vlm_rejects_non_local_base_url():
    assert is_local_vlm_base_url("http://127.0.0.1:11434") is True
    assert is_local_vlm_base_url("http://localhost:11434") is True
    assert is_local_vlm_base_url("https://example.com") is False


def test_disabled_vlm_returns_rule_based_fallback(monkeypatch):
    monkeypatch.setattr(vlm_reasoner.SETTINGS, "vlm_enabled", "disabled")
    monkeypatch.setattr(vlm_reasoner.SETTINGS, "enable_vlm", True)

    reasoner = VlmReasoner(device="cpu", enabled=True)
    text = reasoner.explain_violation(np.zeros((4, 4, 3), dtype=np.uint8), [make_violation()])

    assert reasoner.last_explanation_source == "rule_based"
    assert "Rule-based explanation" in text
    assert "helmet_missing" in text


def test_ollama_vlm_success_uses_prompt_and_marks_source(monkeypatch):
    captured = {}

    def fake_post(url, json, timeout):  # noqa: ARG001
        captured["url"] = url
        captured["json"] = json
        captured["timeout"] = timeout
        return FakeGenerateResponse({"response": "A worker is visible with uncertain helmet evidence due to glare."})

    monkeypatch.setattr(vlm_reasoner.SETTINGS, "vlm_enabled", "auto")
    monkeypatch.setattr(vlm_reasoner.SETTINGS, "enable_vlm", True)
    monkeypatch.setattr(vlm_reasoner.SETTINGS, "vlm_provider", "ollama")
    monkeypatch.setattr(vlm_reasoner.SETTINGS, "vlm_ollama_base_url", "http://127.0.0.1:11434")
    monkeypatch.setattr(vlm_reasoner.SETTINGS, "vlm_model", "llava")
    monkeypatch.setattr(vlm_reasoner.SETTINGS, "vlm_timeout_seconds", 2.0)
    monkeypatch.setattr(vlm_reasoner.SETTINGS, "vlm_max_tokens", 90)
    monkeypatch.setattr(vlm_reasoner.httpx, "post", fake_post)

    reasoner = VlmReasoner(device="cpu", enabled=True)
    text = reasoner.explain_violation(np.zeros((4, 4, 3), dtype=np.uint8), [make_violation()])

    assert text.startswith("A worker is visible")
    assert reasoner.last_explanation_source == "vlm_ollama"
    assert captured["url"] == "http://127.0.0.1:11434/api/generate"
    assert VLM_PROMPT in captured["json"]["prompt"]
    assert captured["json"]["model"] == "llava"
    assert captured["json"]["images"]


def test_auto_vlm_prefers_existing_local_provider_without_ollama(monkeypatch, tmp_path):
    def fail_if_ollama_called(*args, **kwargs):  # noqa: ARG001
        raise AssertionError("auto should prefer the existing local VLM provider")

    def fake_load(self):
        self.provider = "local"
        self._loaded = True

    def fake_local_explain(self, image, violations):  # noqa: ARG001
        self.last_explanation_source = "vlm_local"
        return "Local provider sees limited helmet evidence; review glare and angle."

    model_dir = tmp_path / "vlm_model"
    model_dir.mkdir()
    (model_dir / "config.json").write_text("{}", encoding="utf-8")
    monkeypatch.setattr(vlm_reasoner.SETTINGS, "vlm_enabled", "auto")
    monkeypatch.setattr(vlm_reasoner.SETTINGS, "enable_vlm", True)
    monkeypatch.setattr(vlm_reasoner.SETTINGS, "vlm_provider", "auto")
    monkeypatch.setattr(vlm_reasoner.SETTINGS, "vlm_model_dir", model_dir)
    monkeypatch.setattr(vlm_reasoner, "_local_transformer_available", lambda model_dir: True)  # noqa: ARG005
    monkeypatch.setattr(vlm_reasoner.VlmReasoner, "_load_transformer_provider", fake_load)
    monkeypatch.setattr(vlm_reasoner.VlmReasoner, "_explain_with_transformers", fake_local_explain)
    monkeypatch.setattr(vlm_reasoner.httpx, "post", fail_if_ollama_called)

    reasoner = VlmReasoner(device="cpu", enabled=True)
    text = reasoner.explain_violation(np.zeros((4, 4, 3), dtype=np.uint8), [make_violation()])

    assert reasoner.provider == "local"
    assert reasoner.last_explanation_source == "vlm_local"
    assert text.startswith("Local provider")


def test_auto_vlm_uses_rule_based_when_no_provider_is_available(monkeypatch, tmp_path):
    def fake_get(*args, **kwargs):  # noqa: ARG001
        raise httpx.ConnectError("ollama offline")

    def fail_if_generation_called(*args, **kwargs):  # noqa: ARG001
        raise AssertionError("auto should not call Ollama generation when status is unavailable")

    missing_model_dir = tmp_path / "missing_vlm_model"
    monkeypatch.setattr(vlm_reasoner.SETTINGS, "vlm_enabled", "auto")
    monkeypatch.setattr(vlm_reasoner.SETTINGS, "enable_vlm", True)
    monkeypatch.setattr(vlm_reasoner.SETTINGS, "vlm_provider", "auto")
    monkeypatch.setattr(vlm_reasoner.SETTINGS, "vlm_model_dir", missing_model_dir)
    monkeypatch.setattr(vlm_reasoner.SETTINGS, "vlm_ollama_base_url", "http://127.0.0.1:11434")
    monkeypatch.setattr(vlm_reasoner.httpx, "get", fake_get)
    monkeypatch.setattr(vlm_reasoner.httpx, "post", fail_if_generation_called)

    reasoner = VlmReasoner(device="cpu", enabled=True)
    text = reasoner.explain_violation(np.zeros((4, 4, 3), dtype=np.uint8), [make_violation()])

    assert reasoner.provider == "rule_based"
    assert reasoner.last_explanation_source == "rule_based"
    assert "Rule-based explanation" in text


def test_ollama_timeout_falls_back_to_rule_based(monkeypatch):
    def fake_post(*args, **kwargs):  # noqa: ARG001
        raise httpx.TimeoutException("slow local model")

    monkeypatch.setattr(vlm_reasoner.SETTINGS, "vlm_enabled", "auto")
    monkeypatch.setattr(vlm_reasoner.SETTINGS, "enable_vlm", True)
    monkeypatch.setattr(vlm_reasoner.SETTINGS, "vlm_provider", "ollama")
    monkeypatch.setattr(vlm_reasoner.SETTINGS, "vlm_ollama_base_url", "http://127.0.0.1:11434")
    monkeypatch.setattr(vlm_reasoner.httpx, "post", fake_post)

    reasoner = VlmReasoner(device="cpu", enabled=True)
    text = reasoner.explain_violation(np.zeros((4, 4, 3), dtype=np.uint8), [make_violation()])

    assert reasoner.last_explanation_source == "rule_based"
    assert "Rule-based explanation" in text
