from datetime import datetime, timedelta, timezone

import src.api.jobs as jobs_module
from src.api.jobs import AnalysisSettings, JobStore, execute_analysis_job


def make_settings():
    return AnalysisSettings(fps=1.0, top_k=5, enable_vlm=False, device="cpu")


def test_execution_lock_prevents_duplicate_processing(monkeypatch, tmp_path):
    calls = {"count": 0}

    def fake_run_pipeline(**kwargs):  # noqa: ARG001
        calls["count"] += 1
        return []

    monkeypatch.setattr(jobs_module, "run_pipeline", fake_run_pipeline)
    store = JobStore(tmp_path / "jobs")
    record = store.create_job(
        filename="sample.mp4",
        content=b"video",
        query="worker without helmet",
        settings=make_settings(),
    )

    assert store.acquire_execution_lock(record.job_id) is True
    execute_analysis_job(store, record.job_id)

    assert calls["count"] == 0
    assert store.get(record.job_id).status == "queued"

    store.release_execution_lock(record.job_id)
    execute_analysis_job(store, record.job_id)

    assert calls["count"] == 1
    assert store.get(record.job_id).status == "completed"


def test_stale_active_job_recovery_removes_execution_lock(monkeypatch, tmp_path):
    monkeypatch.setattr(jobs_module.SETTINGS, "stale_running_minutes", 5.0)
    root = tmp_path / "jobs"
    store = JobStore(root)
    record = store.create_job(
        filename="sample.mp4",
        content=b"video",
        query="worker without helmet",
        settings=make_settings(),
    )
    assert store.acquire_execution_lock(record.job_id) is True
    store.update_status(
        record.job_id,
        status="running",
        progress=0.5,
        current_step="Running SafeTrace analysis",
    )
    record.updated_at = datetime.now(timezone.utc) - timedelta(minutes=10)
    store.persist_job(record)

    recovered = JobStore(root).get(record.job_id)

    assert recovered is not None
    assert recovered.status == "failed"
    assert not (recovered.job_dir / "execution.lock").exists()
