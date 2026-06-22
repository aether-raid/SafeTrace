from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient

import src.api.jobs as jobs_module
from src.api.jobs import AnalysisSettings, JobRecord, JobStore
from src.api.server import create_app


def make_settings():
    return AnalysisSettings(fps=1.0, top_k=5, enable_vlm=False, device="cpu")


def test_job_manifest_is_written_on_create_and_update(tmp_path):
    store = JobStore(tmp_path / "jobs")
    record = store.create_job(
        filename="sample.jpg",
        content=b"upload",
        query="worker without helmet",
        settings=make_settings(),
    )

    manifest_path = record.job_dir / "manifest.json"
    assert manifest_path.exists()
    assert '"status": "queued"' in manifest_path.read_text(encoding="utf-8")

    store.update_status(
        record.job_id,
        status="running",
        progress=0.5,
        current_step="Running SafeTrace analysis",
    )

    manifest_text = manifest_path.read_text(encoding="utf-8")
    assert '"status": "running"' in manifest_text
    assert '"startedAt":' in manifest_text


def test_completed_job_can_be_reloaded_from_disk(tmp_path):
    root = tmp_path / "jobs"
    store = JobStore(root)
    record = store.create_job(
        filename="sample.jpg",
        content=b"upload",
        query="worker without helmet",
        settings=make_settings(),
    )
    store.complete_job(
        record.job_id,
        {
            "jobId": record.job_id,
            "status": "completed",
            "media": {"id": "media", "name": "sample.jpg", "type": "image", "sizeBytes": 6},
            "query": "worker without helmet",
            "summary": {
                "framesAnalyzed": 0,
                "framesWithViolations": 0,
                "uniqueViolationTypes": 0,
                "summaryText": "No matching safety violations were detected in the selected frames.",
            },
            "violations": [],
            "frames": [],
            "technicalDetails": {},
        },
    )

    recovered = JobStore(root).get(record.job_id)

    assert recovered is not None
    assert recovered.status == "completed"
    assert recovered.result is not None
    assert recovered.result["jobId"] == record.job_id
    assert recovered.result["technicalDetails"]["jobMetrics"]["statusOutcome"] == "completed"


def test_stale_running_job_is_interrupted_after_recovery(monkeypatch, tmp_path):
    monkeypatch.setattr(jobs_module.SETTINGS, "stale_running_minutes", 5.0)
    root = tmp_path / "jobs"
    store = JobStore(root)
    record = store.create_job(
        filename="sample.jpg",
        content=b"upload",
        query="worker without helmet",
        settings=make_settings(),
    )
    store.update_status(
        record.job_id,
        status="running",
        progress=0.4,
        current_step="Running SafeTrace analysis",
    )
    record.updated_at = datetime.now(timezone.utc) - timedelta(minutes=10)
    store.persist_job(record)

    recovered = JobStore(root).get(record.job_id)

    assert recovered is not None
    assert recovered.status == "failed"
    assert recovered.error == "Job interrupted by backend restart."
    assert recovered.metrics["errorType"] == "InterruptedJob"


def test_delete_job_removes_only_requested_directory(tmp_path):
    store = JobStore(tmp_path / "jobs")
    first = store.create_job(
        filename="first.jpg",
        content=b"first",
        query="first",
        settings=make_settings(),
    )
    second = store.create_job(
        filename="second.jpg",
        content=b"second",
        query="second",
        settings=make_settings(),
    )
    client = TestClient(create_app(store))

    response = client.delete(f"/api/jobs/{first.job_id}")

    assert response.status_code == 200
    assert not first.job_dir.exists()
    assert second.job_dir.exists()


def test_cleanup_removes_expired_completed_jobs(tmp_path):
    store = JobStore(tmp_path / "jobs")
    record = store.create_job(
        filename="sample.jpg",
        content=b"upload",
        query="worker without helmet",
        settings=make_settings(),
    )
    store.complete_job(record.job_id, {"jobId": record.job_id, "status": "completed", "technicalDetails": {}})
    record.finished_at = datetime.now(timezone.utc) - timedelta(hours=2)
    record.updated_at = record.finished_at
    store.persist_job(record)

    removed = store.cleanup_expired_jobs(retention_hours=1)

    assert removed == [record.job_id]
    assert not record.job_dir.exists()


def test_cleanup_does_not_delete_paths_outside_job_root(tmp_path):
    root = tmp_path / "jobs"
    outside = tmp_path / "outside-job"
    outside.mkdir()
    marker = outside / "keep.txt"
    marker.write_text("do not delete", encoding="utf-8")

    store = JobStore(root)
    old = datetime.now(timezone.utc) - timedelta(hours=2)
    unsafe_record = JobRecord(
        job_id="job_outside",
        status="completed",
        progress=1.0,
        current_step="Completed",
        error=None,
        query="",
        settings=make_settings(),
        original_filename="sample.jpg",
        media_type="image",
        size_bytes=1,
        job_dir=outside,
        upload_path=outside / "sample.jpg",
        output_dir=outside / "media",
        created_at=old,
        updated_at=old,
        finished_at=old,
    )
    store._jobs[unsafe_record.job_id] = unsafe_record

    removed = store.cleanup_expired_jobs(retention_hours=1)

    assert removed == []
    assert marker.exists()
