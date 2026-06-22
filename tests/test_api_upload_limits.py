from fastapi.testclient import TestClient

import src.api.server as server_module
from src.api.jobs import JobStore, UploadValidationError, validate_upload_size
from src.api.server import create_app


def make_client(tmp_path):
    app = create_app(JobStore(tmp_path / "jobs"))
    return TestClient(app)


def test_unsupported_upload_extension_is_rejected(tmp_path):
    client = make_client(tmp_path)

    response = client.post(
        "/api/analyze",
        files={"file": ("notes.txt", b"not media", "text/plain")},
        data={"query": "worker without helmet"},
    )

    assert response.status_code == 415
    assert "Unsupported upload type" in response.json()["detail"]["message"]


def test_oversized_upload_is_rejected(monkeypatch, tmp_path):
    monkeypatch.setattr(server_module.SETTINGS, "max_upload_mb", 0.000001)
    client = make_client(tmp_path)

    response = client.post(
        "/api/analyze",
        files={"file": ("sample.jpg", b"too-big", "image/jpeg")},
        data={"query": "worker without helmet"},
    )

    assert response.status_code == 413
    assert "too large" in response.json()["detail"]["message"]


def test_upload_size_validation_function_rejects_oversized_input():
    try:
        validate_upload_size(2, limit_bytes=1)
    except UploadValidationError as exc:
        assert exc.status_code == 413
        assert "too large" in exc.message
    else:
        raise AssertionError("validate_upload_size should reject oversized input")
