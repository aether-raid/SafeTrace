from fastapi.testclient import TestClient

from src.api.jobs import AnalysisSettings, JobStore
from src.api.server import create_app


def test_media_endpoint_serves_only_job_owned_files(tmp_path):
    store = JobStore(tmp_path / "jobs")
    record = store.create_job(
        filename="sample.jpg",
        content=b"upload",
        query="worker without helmet",
        settings=AnalysisSettings(fps=1.0, top_k=5, enable_vlm=False, device="cpu"),
    )
    media_path = record.output_dir / "frame_001_annotated.jpg"
    media_path.write_bytes(b"owned-media")
    store.register_media_file(record.job_id, media_path.name, media_path)

    client = TestClient(create_app(store))

    valid_response = client.get(f"/api/media/{record.job_id}/{media_path.name}")
    assert valid_response.status_code == 200
    assert valid_response.content == b"owned-media"

    traversal_response = client.get(f"/api/media/{record.job_id}/..%2Fsecret.jpg")
    assert traversal_response.status_code == 404

    unregistered_response = client.get(f"/api/media/{record.job_id}/other.jpg")
    assert unregistered_response.status_code == 404

    unknown_job_response = client.get("/api/media/job_missing/frame_001_annotated.jpg")
    assert unknown_job_response.status_code == 404
