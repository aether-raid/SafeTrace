from fastapi.testclient import TestClient

import src.chat_service as chat_service
from src.api.batches import BatchStore
import src.api.jobs as jobs_module
import src.api.server as server_module
from src.api.jobs import JobStore
from src.api.server import create_app


def make_client(tmp_path):
    app = create_app(JobStore(tmp_path / "jobs"), BatchStore(tmp_path / "batches"))
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


def test_cors_allows_local_dev_frontend_origin(tmp_path):
    client = make_client(tmp_path)
    origin = "http://127.0.0.1:5173"

    response = client.options(
        "/api/health",
        headers={
            "Origin": origin,
            "Access-Control-Request-Method": "GET",
        },
    )

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == origin


def test_cors_allows_configured_live_origin_with_private_network_header(monkeypatch, tmp_path):
    origin = "https://safetrace-demo.pages.dev"
    monkeypatch.setenv("SAFETRACE_ALLOWED_ORIGINS", origin)
    client = make_client(tmp_path)

    response = client.options(
        "/api/system/status",
        headers={
            "Origin": origin,
            "Access-Control-Request-Method": "GET",
            "Access-Control-Request-Private-Network": "true",
        },
    )

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == origin
    assert response.headers["access-control-allow-private-network"] == "true"


def test_cors_blocks_unconfigured_origin_and_private_network_header(monkeypatch, tmp_path):
    monkeypatch.setenv("SAFETRACE_ALLOWED_ORIGINS", "https://safetrace-demo.pages.dev")
    client = make_client(tmp_path)

    response = client.options(
        "/api/health",
        headers={
            "Origin": "https://example.invalid",
            "Access-Control-Request-Method": "GET",
            "Access-Control-Request-Private-Network": "true",
        },
    )

    assert response.status_code == 400
    assert "access-control-allow-origin" not in response.headers
    assert "access-control-allow-private-network" not in response.headers


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
    assert body["app_version"]
    assert body["backend_version"]
    assert body["build_mode"] == "development"
    assert body["runtime_layout"] == "source"
    assert body["device"] == "cpu"
    assert body["gpuAvailable"] is False
    assert body["models"]["embeddingModel"]["status"] == "missing"
    assert body["models"]["detector"]["status"] == "missing"
    assert body["models"]["mobileSam"]["status"] == "unavailable"
    assert "MobileSAM is optional" in body["models"]["mobileSam"]["message"]
    assert body["models"]["vlm"]["status"] == "unavailable"
    assert "VLM explanations are optional" in body["models"]["vlm"]["message"]
    assert body["limits"]["maxUploadMb"] > 0
    assert body["limits"]["maxSampledFrames"] > 0
    assert body["limits"]["maxVideoDurationUnlimited"] is True
    assert "No explicit video duration cap" in body["limits"]["maxVideoDurationMessage"]
    assert body["limits"]["embeddingPoolingStrategy"] in {"mean", "max"}
    assert body["queue"]["statusCounts"] == {}


def test_system_status_includes_runtime_preflight_without_loading_chat_model(monkeypatch, tmp_path):
    model_path = tmp_path / "assistant.gguf"
    model_path.write_bytes(b"stub")

    def fail_if_model_loads():
        raise AssertionError("system status should not load the chat model")

    monkeypatch.setattr(server_module, "_gpu_available", lambda: False)
    monkeypatch.setattr(chat_service, "_llama_cpp_runtime_available", lambda: True)
    monkeypatch.setattr(chat_service, "_get_packaged_model", fail_if_model_loads)
    monkeypatch.setattr(chat_service.SETTINGS, "chat_enabled", "auto")
    monkeypatch.setattr(chat_service.SETTINGS, "chat_provider", "packaged_llamacpp")
    monkeypatch.setattr(chat_service.SETTINGS, "chat_model_path", model_path)
    monkeypatch.setattr(chat_service.SETTINGS, "chat_autoload", True)
    monkeypatch.setenv("KMP_DUPLICATE_LIB_OK", "TRUE")
    monkeypatch.setenv("OMP_NUM_THREADS", "1")

    client = make_client(tmp_path)
    response = client.get("/api/system/status")

    assert response.status_code == 200
    body = response.json()
    assert body["runtime"]["backend"]["status"] == "ready"
    assert body["runtime"]["python"]["executable"]
    assert body["runtime"]["workingDirectory"]
    assert body["runtime"]["jobStorePath"]
    assert body["runtime"]["openmp"]["kmpDuplicateLibOk"] is True
    assert body["runtime"]["openmp"]["ompNumThreads"] == "1"
    assert body["runtime"]["chat"]["provider"] == "packaged_llamacpp"
    assert body["runtime"]["chat"]["model_exists"] is True
    assert body["runtime"]["chat"]["runtime_available"] is True
    assert body["preflight"]["checks"]["assistant"]["status"] == "available"
    assert body["preflight"]["checks"]["assistantModel"]["status"] == "ready"
    assert body["preflight"]["checks"]["assistantRuntime"]["status"] == "ready"
    assert body["preflight"]["checks"]["openmp"]["status"] == "ready"


def test_system_status_reports_chat_unavailable_without_ollama(monkeypatch, tmp_path):
    def fail_ollama_check(*args, **kwargs):  # noqa: ARG001
        raise RuntimeError("Ollama is not running")

    monkeypatch.setattr(chat_service.httpx, "get", fail_ollama_check)
    monkeypatch.setattr(chat_service.SETTINGS, "chat_enabled", True)
    monkeypatch.setattr(chat_service.SETTINGS, "chat_provider", "ollama")
    monkeypatch.setattr(chat_service.SETTINGS, "ollama_base_url", "http://127.0.0.1:9")

    client = make_client(tmp_path)
    response = client.get("/api/system/status")

    assert response.status_code == 200
    body = response.json()
    assert body["runtime"]["chat"]["provider"] == "ollama"
    assert body["runtime"]["chat"]["state"] == "unavailable"
    assert body["preflight"]["checks"]["assistant"]["status"] == "unavailable"
    assert "Ollama" in body["preflight"]["checks"]["assistant"]["message"]


def test_system_status_reports_missing_chat_model_structured(monkeypatch, tmp_path):
    missing_model = tmp_path / "missing.gguf"

    monkeypatch.setattr(chat_service.SETTINGS, "chat_enabled", "auto")
    monkeypatch.setattr(chat_service.SETTINGS, "chat_provider", "packaged_llamacpp")
    monkeypatch.setattr(chat_service.SETTINGS, "chat_model_path", missing_model)

    client = make_client(tmp_path)
    response = client.get("/api/system/status")

    assert response.status_code == 200
    body = response.json()
    assert body["runtime"]["chat"]["state"] == "missing_model"
    assert body["runtime"]["chat"]["model_exists"] is False
    assert body["preflight"]["checks"]["assistantModel"]["status"] == "missing"
    assert "GGUF" in body["preflight"]["checks"]["assistantModel"]["actionHint"]
