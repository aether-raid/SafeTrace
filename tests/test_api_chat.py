from fastapi.testclient import TestClient

import src.chat_service as chat_service
from src.api.batches import BatchStore
from src.api.jobs import AnalysisSettings, JobStore
from src.api.server import create_app


def make_client(tmp_path):
    job_store = JobStore(tmp_path / "jobs")
    batch_store = BatchStore(tmp_path / "batches")
    return TestClient(create_app(job_store, batch_store)), job_store, batch_store


def make_settings():
    return AnalysisSettings(fps=1.0, top_k=5, enable_vlm=False, device="cpu")


def reset_packaged_cache(monkeypatch):
    monkeypatch.setattr(chat_service, "_PACKAGED_MODEL", None)
    monkeypatch.setattr(chat_service, "_PACKAGED_MODEL_PATH", None)
    monkeypatch.setattr(chat_service, "_PACKAGED_MODEL_LOADING", False)


def test_chat_status_disabled_when_configured(monkeypatch, tmp_path):
    reset_packaged_cache(monkeypatch)
    monkeypatch.setattr(chat_service.SETTINGS, "chat_enabled", "false")
    monkeypatch.setattr(chat_service.SETTINGS, "chat_provider", "packaged_llamacpp")
    monkeypatch.setattr(chat_service.SETTINGS, "chat_model_path", tmp_path / "missing.gguf")
    client, _job_store, _batch_store = make_client(tmp_path)

    status = client.get("/api/chat/status")
    response = client.post("/api/chat", json={"message": "What does confidence mean?"})

    assert status.status_code == 200
    body = status.json()
    assert body["enabled"] is False
    assert body["state"] == "disabled"
    assert body["status"] == "disabled"
    assert body["enabled_mode"] == "false"
    assert body["provider"] == "packaged_llamacpp"
    assert body["model_exists"] is False
    assert "SAFETRACE_CHAT_ENABLED=false" in body["reason"]
    assert "SAFETRACE_CHAT_ENABLED=auto" in body["action_hint"]
    assert response.status_code == 503
    assert "SAFETRACE_CHAT_ENABLED=false" in response.json()["detail"]["message"]


def test_chat_status_auto_does_not_report_disabled(monkeypatch, tmp_path):
    reset_packaged_cache(monkeypatch)
    missing_model = tmp_path / "missing.gguf"
    monkeypatch.setattr(chat_service.SETTINGS, "chat_enabled", "auto")
    monkeypatch.setattr(chat_service.SETTINGS, "chat_provider", "packaged_llamacpp")
    monkeypatch.setattr(chat_service.SETTINGS, "chat_model_path", missing_model)
    client, _job_store, _batch_store = make_client(tmp_path)

    status = client.get("/api/chat/status")

    assert status.status_code == 200
    body = status.json()
    assert body["enabled"] is True
    assert body["enabled_mode"] == "auto"
    assert body["state"] == "missing_model"
    assert body["state"] != "disabled"


def test_packaged_provider_reports_missing_model(monkeypatch, tmp_path):
    reset_packaged_cache(monkeypatch)
    missing_model = tmp_path / "missing.gguf"

    def fail_ollama_check(*args, **kwargs):  # noqa: ARG001
        raise AssertionError("Packaged provider should not require Ollama")

    monkeypatch.setattr(chat_service.httpx, "get", fail_ollama_check)
    monkeypatch.setattr(chat_service.SETTINGS, "chat_enabled", "auto")
    monkeypatch.setattr(chat_service.SETTINGS, "chat_provider", "packaged_llamacpp")
    monkeypatch.setattr(chat_service.SETTINGS, "chat_model_path", missing_model)
    client, _job_store, _batch_store = make_client(tmp_path)

    status = client.get("/api/chat/status")
    response = client.post("/api/chat", json={"message": "What does SafeTrace confidence mean?"})

    assert status.status_code == 200
    body = status.json()
    assert body["enabled"] is True
    assert body["available"] is False
    assert body["state"] == "missing_model"
    assert body["status"] == "missing_model"
    assert body["model_exists"] is False
    assert body["model_path"] == str(missing_model)
    assert "Place the GGUF model" in body["action_hint"]
    assert response.status_code == 503
    assert "missing" in response.json()["detail"]["message"].lower()


def test_fast_speed_profile_is_reported_without_model(monkeypatch, tmp_path):
    reset_packaged_cache(monkeypatch)
    monkeypatch.setattr(chat_service.SETTINGS, "chat_enabled", "auto")
    monkeypatch.setattr(chat_service.SETTINGS, "chat_provider", "packaged_llamacpp")
    monkeypatch.setattr(chat_service.SETTINGS, "chat_model_path", tmp_path / "missing.gguf")
    monkeypatch.setattr(chat_service.SETTINGS, "chat_speed_profile", "fast")
    client, _job_store, _batch_store = make_client(tmp_path)

    status = client.get("/api/chat/status")

    assert status.status_code == 200
    assert status.json()["speed_profile"] == "fast"
    assert status.json()["state"] == "missing_model"


def test_packaged_provider_reports_missing_runtime(monkeypatch, tmp_path):
    reset_packaged_cache(monkeypatch)
    model_path = tmp_path / "local-model.gguf"
    model_path.write_bytes(b"not a real model")
    original_find_spec = chat_service.importlib.util.find_spec

    def fake_find_spec(name):
        if name == "llama_cpp":
            return None
        return original_find_spec(name)

    monkeypatch.setattr(chat_service.importlib.util, "find_spec", fake_find_spec)
    monkeypatch.setattr(chat_service.SETTINGS, "chat_enabled", "auto")
    monkeypatch.setattr(chat_service.SETTINGS, "chat_provider", "packaged_llamacpp")
    monkeypatch.setattr(chat_service.SETTINGS, "chat_model_path", model_path)
    client, _job_store, _batch_store = make_client(tmp_path)

    status = client.get("/api/chat/status")
    response = client.post("/api/chat", json={"message": "What does SafeTrace confidence mean?"})

    assert status.status_code == 200
    body = status.json()
    assert body["enabled"] is True
    assert body["available"] is False
    assert body["state"] == "missing_runtime"
    assert body["status"] == "missing_runtime"
    assert body["model_exists"] is True
    assert body["runtime_available"] is False
    assert "llama-cpp-python" in body["action_hint"]
    assert response.status_code == 503
    assert "runtime" in response.json()["detail"]["message"].lower()


def test_chat_refuses_out_of_scope_question_before_provider(monkeypatch, tmp_path):
    reset_packaged_cache(monkeypatch)
    monkeypatch.setattr(chat_service.SETTINGS, "chat_enabled", "auto")
    monkeypatch.setattr(chat_service.SETTINGS, "chat_provider", "packaged_llamacpp")
    monkeypatch.setattr(chat_service.SETTINGS, "chat_model_path", tmp_path / "missing.gguf")
    client, _job_store, _batch_store = make_client(tmp_path)

    response = client.post("/api/chat", json={"message": "What is the weather?"})

    assert response.status_code == 200
    body = response.json()
    assert body["safeTraceOnly"] is True
    assert body["sources"] == []
    assert "only answer questions about SafeTrace" in body["answer"]
    assert body["modelProvider"] == "packaged_llamacpp"


def test_chat_mock_provider_uses_job_context(monkeypatch, tmp_path):
    reset_packaged_cache(monkeypatch)
    monkeypatch.setattr(chat_service.SETTINGS, "chat_enabled", True)
    monkeypatch.setattr(chat_service.SETTINGS, "chat_provider", "mock")
    client, job_store, _batch_store = make_client(tmp_path)
    record = job_store.create_job(
        filename="sample.mp4",
        content=b"video",
        query="worker without helmet",
        settings=make_settings(),
    )
    job_store.complete_job(
        record.job_id,
        {
            "jobId": record.job_id,
            "status": "completed",
            "media": {"id": "media", "name": "sample.mp4", "type": "video", "sizeBytes": 5},
            "query": "worker without helmet",
            "summary": {
                "framesAnalyzed": 2,
                "framesWithViolations": 1,
                "uniqueViolationTypes": 1,
                "summaryText": "Missing helmet found.",
                "potentialEventCount": 1,
                "overallConfidence": 0.91,
            },
            "violations": [
                {
                    "id": "helmet_missing",
                    "name": "Missing Helmet",
                    "severity": "high",
                    "description": "Worker without helmet.",
                    "affectedFrames": [
                        {
                            "frameId": "frame_001",
                            "frameNumber": 1,
                            "timestamp": "00:00:05",
                            "confidence": 0.91,
                        }
                    ],
                    "confidenceMin": 0.91,
                    "confidenceMax": 0.91,
                }
            ],
            "frames": [],
            "technicalDetails": {},
        },
    )

    response = client.post(
        "/api/chat",
        json={
            "message": "Which frames support this SafeTrace finding?",
            "job_id": record.job_id,
            "include_current_result": True,
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["modelProvider"] == "mock"
    assert "job_result" in body["sources"]
    assert "docs" in body["sources"]


def test_chat_ollama_unavailable_is_structured(monkeypatch, tmp_path):
    reset_packaged_cache(monkeypatch)
    monkeypatch.setattr(chat_service.SETTINGS, "chat_enabled", True)
    monkeypatch.setattr(chat_service.SETTINGS, "chat_provider", "ollama")
    monkeypatch.setattr(chat_service.SETTINGS, "ollama_base_url", "http://127.0.0.1:9")
    monkeypatch.setattr(chat_service.SETTINGS, "chat_timeout_seconds", 0.1)
    client, _job_store, _batch_store = make_client(tmp_path)

    status = client.get("/api/chat/status")
    response = client.post("/api/chat", json={"message": "What does SafeTrace confidence mean?"})

    assert status.status_code == 200
    assert status.json()["state"] == "unavailable"
    assert response.status_code == 503
    assert "Ollama" in response.json()["detail"]["message"]
