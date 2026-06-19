from fastapi.testclient import TestClient

import src.api.jobs as jobs_module
import src.api.server as server_module
from src.api.jobs import JobStore
from src.api.server import create_app


def make_client(tmp_path):
    app = create_app(JobStore(tmp_path / "jobs"))
    return TestClient(app)


def test_health_does_not_instantiate_pipeline(monkeypatch, tmp_path):
    def fail_if_called(**kwargs):  # noqa: ARG001
        raise AssertionError("pipeline should not run for health checks")

    monkeypatch.setattr(jobs_module, "run_pipeline", fail_if_called)
    client = make_client(tmp_path)

    response = client.get("/api/health")

    assert response.status_code == 200
    assert response.json()["status"] == "ok"
    assert response.json()["api"] == "safetrace-local"


def test_system_status_reports_missing_paths_without_loading_models(monkeypatch, tmp_path):
    monkeypatch.setattr(server_module, "_gpu_available", lambda: False)
    monkeypatch.setattr(server_module.SETTINGS, "device", "cpu")
    monkeypatch.setattr(server_module.SETTINGS, "enable_vlm", True)
    monkeypatch.setattr(server_module.SETTINGS, "siglip_model_dir", tmp_path / "missing-siglip")
    monkeypatch.setattr(server_module.SETTINGS, "yolo_checkpoint", tmp_path / "missing-yolo.pt")
    monkeypatch.setattr(server_module.SETTINGS, "yolo_fallback_checkpoint", tmp_path / "missing-fallback.pt")
    monkeypatch.setattr(server_module.SETTINGS, "mobile_sam_checkpoint", tmp_path / "missing-mobile-sam.pt")
    monkeypatch.setattr(server_module.SETTINGS, "vlm_model_dir", tmp_path / "missing-vlm")

    client = make_client(tmp_path)
    response = client.get("/api/system/status")

    assert response.status_code == 200
    body = response.json()
    assert body["device"] == "cpu"
    assert body["gpuAvailable"] is False
    assert body["models"]["embeddingModel"]["status"] == "missing"
    assert body["models"]["detector"]["status"] == "missing"
    assert body["models"]["mobileSam"]["status"] == "unavailable"
    assert body["models"]["vlm"]["status"] == "unavailable"
