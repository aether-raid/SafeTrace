from fastapi.testclient import TestClient

import src.api.jobs as jobs_module
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
    assert "secret checkpoint traceback" not in status["error"]

    result_response = client.get(f"/api/jobs/{job_id}/result")
    assert result_response.status_code == 409
    assert result_response.json()["detail"]["message"] == status["error"]


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
