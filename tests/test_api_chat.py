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


def llama_diagnostics(*, import_ok: bool, spec_found: bool | None = None, error_type: str | None = None):
    spec = import_ok if spec_found is None else spec_found
    return {
        "backendPythonExecutable": r"C:\Python312\python.exe" if not import_ok else r"C:\repo\.venv\Scripts\python.exe",
        "expectedVenvPython": r"C:\repo\.venv\Scripts\python.exe",
        "expectedVenvPythonExists": True,
        "runningInExpectedVenv": import_ok,
        "specFound": spec,
        "importOk": import_ok,
        "importStatus": "ok" if import_ok else "import_error" if spec else "missing",
        "importErrorType": error_type,
        "importErrorMessage": "native DLL load failed" if error_type else None,
        "setupCommand": r".venv\Scripts\python.exe -m pip install llama-cpp-python",
        "restartRequired": "Restart the SafeTrace backend after installing llama-cpp-python.",
    }


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

    monkeypatch.setattr(chat_service, "_llama_cpp_runtime_diagnostics", lambda: llama_diagnostics(import_ok=False))
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
    assert body["python_executable"] == r"C:\Python312\python.exe"
    assert body["expected_venv_python"] == r"C:\repo\.venv\Scripts\python.exe"
    assert body["running_in_expected_venv"] is False
    assert body["llama_cpp_import_status"] == "missing"
    assert body["llama_cpp_spec_found"] is False
    assert body["setup_command"] == r".venv\Scripts\python.exe -m pip install llama-cpp-python"
    assert "Restart the SafeTrace backend" in body["restart_required"]
    assert body["runtime_diagnostics"]["backendPythonExecutable"] == r"C:\Python312\python.exe"
    assert body["fallback_available"] is True
    assert body["fallback_label"] == "Limited SafeTrace help"
    assert "llama-cpp-python" in body["action_hint"]
    assert ".venv\\Scripts\\python.exe -m pip install llama-cpp-python" in body["action_hint"]
    assert response.status_code == 200
    response_body = response.json()
    assert response_body["safeTraceOnly"] is True
    assert response_body["modelProvider"] == "packaged_llamacpp_deterministic_fallback"
    assert "Overall confidence" in response_body["answer"]
    assert "docs" in response_body["sources"]


def test_packaged_missing_runtime_generic_help_uses_deterministic_fallback(monkeypatch, tmp_path):
    reset_packaged_cache(monkeypatch)
    model_path = tmp_path / "local-model.gguf"
    model_path.write_bytes(b"not a real model")

    monkeypatch.setattr(chat_service, "_llama_cpp_runtime_diagnostics", lambda: llama_diagnostics(import_ok=False))
    monkeypatch.setattr(chat_service.SETTINGS, "chat_enabled", "auto")
    monkeypatch.setattr(chat_service.SETTINGS, "chat_provider", "packaged_llamacpp")
    monkeypatch.setattr(chat_service.SETTINGS, "chat_model_path", model_path)
    client, _job_store, _batch_store = make_client(tmp_path)

    response = client.post("/api/chat", json={"message": "Can I use SafeTrace offline?"})

    assert response.status_code == 200
    body = response.json()
    assert body["modelProvider"] == "packaged_llamacpp_deterministic_fallback"
    assert "Limited SafeTrace help" in body["answer"]
    assert "llama-cpp-python" in body["answer"]


def test_packaged_provider_reports_llama_cpp_import_error(monkeypatch, tmp_path):
    reset_packaged_cache(monkeypatch)
    model_path = tmp_path / "local-model.gguf"
    model_path.write_bytes(b"not a real model")

    monkeypatch.setattr(
        chat_service,
        "_llama_cpp_runtime_diagnostics",
        lambda: llama_diagnostics(import_ok=False, spec_found=True, error_type="OSError"),
    )
    monkeypatch.setattr(chat_service.SETTINGS, "chat_enabled", "auto")
    monkeypatch.setattr(chat_service.SETTINGS, "chat_provider", "packaged_llamacpp")
    monkeypatch.setattr(chat_service.SETTINGS, "chat_model_path", model_path)
    client, _job_store, _batch_store = make_client(tmp_path)

    status = client.get("/api/chat/status")

    assert status.status_code == 200
    body = status.json()
    assert body["state"] == "missing_runtime"
    assert body["llama_cpp_import_status"] == "import_error"
    assert body["llama_cpp_spec_found"] is True
    assert body["llama_cpp_import_error_type"] == "OSError"
    assert "native DLL load failed" in body["llama_cpp_import_error_message"]
    assert "importing llama_cpp failed" in body["reason"]


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


def test_chat_accepts_custom_typed_safetrace_usage_question(monkeypatch, tmp_path):
    reset_packaged_cache(monkeypatch)
    monkeypatch.setattr(chat_service.SETTINGS, "chat_enabled", True)
    monkeypatch.setattr(chat_service.SETTINGS, "chat_provider", "mock")
    client, _job_store, _batch_store = make_client(tmp_path)

    response = client.post("/api/chat", json={"message": "Can I use this offline?"})

    assert response.status_code == 200
    body = response.json()
    assert body["modelProvider"] == "mock"
    assert body["safeTraceOnly"] is True
    assert "SafeTrace Assistant test response" in body["answer"]
    assert "docs" in body["sources"]


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


def complete_driver_result(job_store, record):
    job_store.complete_job(
        record.job_id,
        {
            "jobId": record.job_id,
            "status": "completed",
            "media": {"id": "media", "name": "driver-cab.mp4", "type": "video", "sizeBytes": 5},
            "query": "driver seatbelt and phone use",
            "summary": {
                "framesAnalyzed": 5,
                "framesWithViolations": 1,
                "uniqueViolationTypes": 2,
                "summaryText": "Missing seatbelt and helmet evidence need review.",
                "potentialEventCount": 2,
                "overallConfidence": 1.0,
            },
            "violations": [
                {
                    "id": "seatbelt_missing",
                    "name": "Missing Seatbelt",
                    "severity": "Medium",
                    "description": "Driver torso detected without an overlapping seatbelt.",
                    "affectedFrames": [
                        {
                            "frameId": "frame_005",
                            "frameNumber": 5,
                            "timestamp": "00:00:04",
                            "confidence": 1.0,
                        }
                    ],
                    "confidenceMin": 1.0,
                    "confidenceMax": 1.0,
                },
                {
                    "id": "helmet_missing",
                    "name": "Missing Helmet",
                    "severity": "High",
                    "description": "Person head detected without an overlapping helmet.",
                    "affectedFrames": [
                        {
                            "frameId": "frame_005",
                            "frameNumber": 5,
                            "timestamp": "00:00:04",
                            "confidence": 1.0,
                        }
                    ],
                    "confidenceMin": 1.0,
                    "confidenceMax": 1.0,
                },
            ],
            "frames": [],
            "technicalDetails": {},
        },
    )


def ask_api(client, message: str, job_id: str | None = None):
    payload = {"message": message, "include_current_result": True}
    if job_id:
        payload["job_id"] = job_id
    return client.post("/api/chat", json=payload)


def test_chat_api_seatbelt_question_uses_selected_result(monkeypatch, tmp_path):
    reset_packaged_cache(monkeypatch)
    monkeypatch.setattr(chat_service.SETTINGS, "chat_enabled", True)
    monkeypatch.setattr(chat_service.SETTINGS, "chat_provider", "mock")
    client, job_store, _batch_store = make_client(tmp_path)
    record = job_store.create_job(
        filename="driver-cab.mp4",
        content=b"video",
        query="driver seatbelt and phone use",
        settings=make_settings(),
    )
    complete_driver_result(job_store, record)

    response = ask_api(client, "Was the driver wearing a seatbelt?", record.job_id)

    assert response.status_code == 200
    body = response.json()
    assert "job_result" in body["sources"]
    assert "Video: driver-cab.mp4" in body["answer"]
    assert f"Job: {record.job_id}" in body["answer"]
    assert "SafeTrace flagged Missing Seatbelt." in body["answer"]
    assert "Frame 5 at 00:00:04 (100%)" in body["answer"]
    assert "manual confirmation" in body["answer"]


def test_chat_api_phone_question_without_phone_finding_does_not_hallucinate(monkeypatch, tmp_path):
    reset_packaged_cache(monkeypatch)
    monkeypatch.setattr(chat_service.SETTINGS, "chat_enabled", True)
    monkeypatch.setattr(chat_service.SETTINGS, "chat_provider", "mock")
    client, job_store, _batch_store = make_client(tmp_path)
    record = job_store.create_job(
        filename="driver-cab.mp4",
        content=b"video",
        query="driver seatbelt and phone use",
        settings=make_settings(),
    )
    complete_driver_result(job_store, record)

    response = ask_api(client, "Is the driver using a phone while driving?", record.job_id)

    assert response.status_code == 200
    answer = response.json()["answer"]
    assert "SafeTrace did not detect a phone-use violation in this result." in answer
    assert "may not reliably support phone-use detection" in answer
    assert "SafeTrace flagged Phone" not in answer


def test_chat_api_no_selected_result_instructs_user(monkeypatch, tmp_path):
    reset_packaged_cache(monkeypatch)
    monkeypatch.setattr(chat_service.SETTINGS, "chat_enabled", True)
    monkeypatch.setattr(chat_service.SETTINGS, "chat_provider", "mock")
    client, _job_store, _batch_store = make_client(tmp_path)

    response = ask_api(client, "Was the driver wearing a seatbelt?")

    assert response.status_code == 200
    answer = response.json()["answer"]
    assert "selected completed SafeTrace result" in answer
    assert "pass its job_id to /api/chat" in answer


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
