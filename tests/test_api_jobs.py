import time

from fastapi.testclient import TestClient

import src.api.jobs as jobs_module
import src.api.server as server_module
from src.api.jobs import JobStore
from src.api.server import create_app


def make_client(tmp_path):
    app = create_app(JobStore(tmp_path / "jobs"))
    return TestClient(app)


def completed_status(client, job_id):
    response = client.get(f"/api/jobs/{job_id}")
    assert response.status_code == 200
    return response.json()


def test_analyze_completes_with_monkeypatched_pipeline(monkeypatch, tmp_path):
    annotated = tmp_path / "frame_000046_annotated.jpg"
    annotated.write_bytes(b"fake-jpeg-bytes")

    def fake_run_pipeline(**kwargs):
        assert kwargs["query"] == "worker without helmet"
        assert kwargs["fps"] == 1.0
        assert kwargs["top_k"] == 5
        assert kwargs["device"] == "cpu"
        assert kwargs["enable_vlm"] is False
        assert kwargs["upload_path"].exists()
        return [
            {
                "frame_id": "video_20260618_000046",
                "frame_path": "data/frames/video_20260618_000046.jpg",
                "score": 0.059,
                "detections": [{"label": "person", "confidence": 0.97, "bbox": [1, 2, 3, 4]}],
                "violations": [
                    {
                        "name": "helmet_missing",
                        "severity": "high",
                        "confidence": 0.98,
                        "description": "Worker head detected without overlapping helmet.",
                    }
                ],
                "explanation": "A worker is visible without helmet overlap.",
                "annotated_path": str(annotated),
            },
            {
                "frame_id": "video_20260618_000047",
                "frame_path": "data/frames/video_20260618_000047.jpg",
                "score": 0.041,
                "detections": [],
                "violations": [],
                "explanation": None,
                "annotated_path": None,
            },
        ]

    monkeypatch.setattr(jobs_module, "run_pipeline", fake_run_pipeline)
    client = make_client(tmp_path)

    response = client.post(
        "/api/analyze",
        files={"file": ("sample.jpg", b"tiny image", "image/jpeg")},
        data={
            "query": "worker without helmet",
            "fps": "1.0",
            "topK": "5",
            "enableVlm": "false",
            "device": "cpu",
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "queued"

    job_id = body["jobId"]
    status = completed_status(client, job_id)
    assert status["status"] == "completed"
    assert status["progress"] == 1.0
    assert status["progressPercent"] == 100
    assert status["stage"] == "completed"
    assert status["message"] == "Analysis completed"
    assert status["updatedAt"]
    assert status["startedAt"]
    assert status["finishedAt"]
    assert status["heartbeatAt"] is None
    diagnostics = status["componentDiagnostics"]
    assert diagnostics["safeMode"] is False
    assert diagnostics["embeddingRequested"] is True
    assert diagnostics["vlmEffectiveEnabled"] is False
    assert diagnostics["currentPipelineStage"] == "completed"

    result_response = client.get(f"/api/jobs/{job_id}/result")
    assert result_response.status_code == 200
    result = result_response.json()
    assert result["jobId"] == job_id
    assert result["status"] == "completed"
    assert result["media"]["name"] == "sample.jpg"
    assert result["summary"]["framesAnalyzed"] == 2
    assert result["summary"]["framesWithViolations"] == 1
    assert result["violations"][0]["name"] == "Missing Helmet"
    assert result["frames"][0]["imageUrl"].startswith(f"/api/media/{job_id}/")
    assert result["frames"][1]["imageUrl"] is None
    assert "No annotated evidence image" in result["frames"][1]["imageMessage"]

    media_response = client.get(result["frames"][0]["imageUrl"])
    assert media_response.status_code == 200
    assert media_response.content == b"fake-jpeg-bytes"

    report_response = client.get(f"/api/reports/{job_id}/technical-json")
    assert report_response.status_code == 200
    assert report_response.json()["technicalDetails"]["job"]["status"] == "completed"


def test_failed_analysis_returns_structured_error(monkeypatch, tmp_path):
    def failing_pipeline(**kwargs):  # noqa: ARG001
        raise RuntimeError("secret checkpoint traceback")

    monkeypatch.setattr(jobs_module, "run_pipeline", failing_pipeline)
    client = make_client(tmp_path)

    response = client.post(
        "/api/analyze",
        files={"file": ("sample.jpg", b"tiny image", "image/jpeg")},
        data={"query": "worker without helmet"},
    )

    assert response.status_code == 200
    job_id = response.json()["jobId"]
    status = completed_status(client, job_id)
    assert status["status"] == "failed"
    assert status["progressPercent"] == 100
    assert status["stage"] == "failed"
    assert status["message"] == "Analysis failed"
    assert status["finishedAt"]
    assert status["heartbeatAt"] is None
    assert "secret checkpoint traceback" not in status["error"]
    assert status["metrics"]["errorType"] == "RuntimeError"
    assert status["metrics"]["errorMessage"] == "Analysis could not be completed. Please try again."
    assert status["componentDiagnostics"]["errorType"] == "RuntimeError"

    result_response = client.get(f"/api/jobs/{job_id}/result")
    assert result_response.status_code == 409
    assert result_response.json()["detail"]["message"] == status["error"]


def test_running_job_heartbeat_updates_message_and_timestamp(tmp_path):
    store = JobStore(tmp_path / "jobs")
    record = store.create_job(
        filename="sample.jpg",
        content=b"tiny image",
        query="worker without helmet",
        settings=jobs_module.AnalysisSettings(fps=1.0, top_k=5, enable_vlm=False, device="cpu"),
    )
    store.update_status(
        record.job_id,
        status="running",
        progress=0.35,
        current_step="Running SafeTrace analysis. This stage may take a few minutes.",
    )
    before = store.require(record.job_id).status_payload()

    assert store.heartbeat(
        record.job_id,
        progress=0.35,
        current_step="Running SafeTrace analysis. Still working locally after 8s; sampling evidence.",
    )

    after = store.require(record.job_id).status_payload()
    assert after["status"] == "running"
    assert after["stage"] == "analyzing"
    assert after["progressPercent"] == 35
    assert "Still working locally" in after["message"]
    assert after["heartbeatAt"]
    assert after["updatedAt"] >= before["updatedAt"]

    store.complete_job(record.job_id, {"technicalDetails": {}})
    assert store.heartbeat(record.job_id, current_step="Should not update") is False


def test_analyze_uses_selected_vlm_profile_from_backend_settings(monkeypatch, tmp_path):
    lightweight = tmp_path / "models" / "vlm" / "lightweight-256m"
    root_vlm = tmp_path / "models" / "vlm"
    lightweight.mkdir(parents=True)
    (lightweight / "model.safetensors").write_bytes(b"placeholder")
    captured = []

    def fake_run_pipeline(**kwargs):
        captured.append(kwargs)
        return []

    monkeypatch.setattr(server_module.SETTINGS, "vlm_profile", "rule_based")
    monkeypatch.setattr(server_module.SETTINGS, "vlm_model_dir", root_vlm)
    monkeypatch.setattr(server_module.SETTINGS, "vlm_lightweight_model_path", lightweight)
    monkeypatch.setattr(server_module.SETTINGS, "enable_vlm", False)
    monkeypatch.setattr(jobs_module.SETTINGS, "vlm_lightweight_model_path", lightweight)
    monkeypatch.setattr(jobs_module, "run_pipeline", fake_run_pipeline)
    client = make_client(tmp_path)

    settings_response = client.post(
        "/api/system/vlm/settings",
        json={"selectedProfile": "lightweight_256m", "enabled": True},
    )
    assert settings_response.status_code == 200

    response = client.post(
        "/api/analyze",
        files={"file": ("sample.jpg", b"tiny image", "image/jpeg")},
        data={
            "query": "worker without helmet",
            "enableVlm": "true",
            "device": "cpu",
        },
    )

    assert response.status_code == 200
    assert captured
    assert captured[0]["enable_vlm"] is True
    assert captured[0]["vlm_profile"] == "lightweight_256m"
    assert captured[0]["vlm_model_dir"] == lightweight
    assert captured[0]["vlm_model_dir"] != root_vlm


def test_analyze_rule_based_does_not_request_vlm_profile_load(monkeypatch, tmp_path):
    captured = []

    def fake_run_pipeline(**kwargs):
        captured.append(kwargs)
        return []

    monkeypatch.setattr(jobs_module, "run_pipeline", fake_run_pipeline)
    client = make_client(tmp_path)

    response = client.post(
        "/api/analyze",
        files={"file": ("sample.jpg", b"tiny image", "image/jpeg")},
        data={
            "query": "worker without helmet",
            "enableVlm": "true",
            "vlmProfile": "rule_based",
            "vlmEnabled": "true",
            "device": "cpu",
        },
    )

    assert response.status_code == 200
    assert captured
    assert captured[0]["enable_vlm"] is False
    assert captured[0]["vlm_profile"] == "rule_based"
    assert captured[0]["vlm_model_dir"] is None


def test_analyze_visual_explanations_off_does_not_request_vlm(monkeypatch, tmp_path):
    lightweight = tmp_path / "models" / "vlm" / "lightweight-256m"
    lightweight.mkdir(parents=True)
    (lightweight / "model.safetensors").write_bytes(b"placeholder")
    captured = []

    def fake_run_pipeline(**kwargs):
        captured.append(kwargs)
        return []

    monkeypatch.setattr(jobs_module.SETTINGS, "vlm_lightweight_model_path", lightweight)
    monkeypatch.setattr(jobs_module, "run_pipeline", fake_run_pipeline)
    client = make_client(tmp_path)

    response = client.post(
        "/api/analyze",
        files={"file": ("sample.jpg", b"tiny image", "image/jpeg")},
        data={
            "query": "worker without helmet",
            "enableVlm": "false",
            "vlmProfile": "lightweight_256m",
            "vlmEnabled": "true",
            "device": "cpu",
        },
    )

    assert response.status_code == 200
    assert captured
    assert captured[0]["enable_vlm"] is False
    assert captured[0]["vlm_profile"] == "lightweight_256m"
    assert captured[0]["vlm_model_dir"] is None


def test_analyze_hard_disabled_vlm_cannot_be_activated(monkeypatch, tmp_path):
    lightweight = tmp_path / "models" / "vlm" / "lightweight-256m"
    lightweight.mkdir(parents=True)
    (lightweight / "model.safetensors").write_bytes(b"placeholder")
    captured = []

    def fake_run_pipeline(**kwargs):
        captured.append(kwargs)
        return []

    monkeypatch.setattr(server_module.SETTINGS, "vlm_profile", "rule_based")
    monkeypatch.setattr(server_module.SETTINGS, "enable_vlm", False)
    monkeypatch.setattr(server_module.SETTINGS, "vlm_enabled", "false")
    monkeypatch.setattr(server_module.SETTINGS, "vlm_lightweight_model_path", lightweight)
    monkeypatch.setattr(jobs_module.SETTINGS, "vlm_enabled", "false")
    monkeypatch.setattr(jobs_module, "run_pipeline", fake_run_pipeline)
    client = make_client(tmp_path)

    settings_response = client.post(
        "/api/system/vlm/settings",
        json={"selectedProfile": "lightweight_256m", "enabled": True},
    )
    assert settings_response.status_code == 200
    assert settings_response.json()["active"] is False

    response = client.post(
        "/api/analyze",
        files={"file": ("sample.jpg", b"tiny image", "image/jpeg")},
        data={
            "query": "worker without helmet",
            "enableVlm": "true",
            "vlmProfile": "lightweight_256m",
            "vlmEnabled": "true",
            "device": "cpu",
        },
    )

    assert response.status_code == 200
    assert captured
    assert captured[0]["enable_vlm"] is False
    assert captured[0]["vlm_profile"] == "lightweight_256m"
    assert captured[0]["vlm_model_dir"] is None


def test_safe_mode_suppresses_vlm_and_forces_cpu(monkeypatch, tmp_path):
    lightweight = tmp_path / "models" / "vlm" / "lightweight-256m"
    lightweight.mkdir(parents=True)
    (lightweight / "model.safetensors").write_bytes(b"placeholder")
    captured = []

    def fake_run_pipeline(**kwargs):
        captured.append(kwargs)
        diagnostics = kwargs["component_diagnostics"]
        diagnostics.update(
            {
                "safeMode": True,
                "device": "cpu",
                "embeddingRequested": False,
                "embeddingLoaded": False,
                "vlmAttempted": False,
                "vlmLoaded": False,
                "mobileSamRequested": False,
                "mobileSamLoaded": False,
                "currentPipelineStage": "safe_direct_frame_scan",
            }
        )
        return []

    monkeypatch.setattr(server_module.SETTINGS, "analysis_safe_mode", True)
    monkeypatch.setattr(server_module.SETTINGS, "vlm_lightweight_model_path", lightweight)
    monkeypatch.setattr(jobs_module.SETTINGS, "analysis_safe_mode", True)
    monkeypatch.setattr(jobs_module, "run_pipeline", fake_run_pipeline)
    client = make_client(tmp_path)

    settings_response = client.post(
        "/api/system/vlm/settings",
        json={"selectedProfile": "lightweight_256m", "enabled": True},
    )
    assert settings_response.status_code == 200
    settings_body = settings_response.json()
    assert settings_body["enabled"] is False
    assert settings_body["active"] is False
    assert settings_body["actualExplanationMode"] == "rule_based"
    assert settings_body["vlmSuppressedReason"] == "safe_mode"

    response = client.post(
        "/api/analyze",
        files={"file": ("sample.jpg", b"tiny image", "image/jpeg")},
        data={
            "query": "worker without helmet",
            "enableVlm": "true",
            "vlmProfile": "lightweight_256m",
            "vlmEnabled": "true",
            "device": "cuda",
        },
    )

    assert response.status_code == 200
    assert captured
    assert captured[0]["safe_mode"] is True
    assert captured[0]["device"] == "cpu"
    assert captured[0]["enable_vlm"] is False
    assert captured[0]["vlm_model_dir"] is None
    status = completed_status(client, response.json()["jobId"])
    diagnostics = status["componentDiagnostics"]
    assert diagnostics["safeMode"] is True
    assert diagnostics["device"] == "cpu"
    assert diagnostics["embeddingRequested"] is False
    assert diagnostics["vlmLoaded"] is False
    assert diagnostics["mobileSamLoaded"] is False


def test_pipeline_timeout_marks_job_failed_with_component_diagnostics(monkeypatch, tmp_path):
    def slow_pipeline(**kwargs):
        kwargs["component_diagnostics"]["currentPipelineStage"] = "embedding_model_load"
        time.sleep(0.2)
        return []

    monkeypatch.setattr(jobs_module.SETTINGS, "analysis_job_timeout_seconds", 0.01)
    monkeypatch.setattr(jobs_module, "run_pipeline", slow_pipeline)
    client = make_client(tmp_path)

    response = client.post(
        "/api/analyze",
        files={"file": ("sample.jpg", b"tiny image", "image/jpeg")},
        data={"query": "worker without helmet", "device": "cpu"},
    )

    assert response.status_code == 200
    status = completed_status(client, response.json()["jobId"])
    assert status["status"] == "failed"
    assert status["message"] == "Analysis failed"
    assert status["metrics"]["errorType"] == "PipelineTimeoutError"
    assert status["componentDiagnostics"]["errorType"] == "PipelineTimeoutError"
    assert status["componentDiagnostics"]["currentPipelineStage"] == "embedding_model_load"


def test_analyze_rejects_invalid_requests(tmp_path):
    client = make_client(tmp_path)

    empty_query = client.post(
        "/api/analyze",
        files={"file": ("sample.jpg", b"tiny image", "image/jpeg")},
        data={"query": "   "},
    )
    assert empty_query.status_code == 400
    assert empty_query.json()["detail"]["message"] == "Query is required"

    empty_file = client.post(
        "/api/analyze",
        files={"file": ("sample.jpg", b"", "image/jpeg")},
        data={"query": "worker without helmet"},
    )
    assert empty_file.status_code == 400
    assert empty_file.json()["detail"]["message"] == "Uploaded file is empty"
