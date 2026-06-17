from src.jobs import JobStore
from src.uploads import UploadedMedia


def test_job_is_queued_and_status_updates_are_stored(workspace_tmp):
    store = JobStore(root=workspace_tmp)
    job = store.create_job(
        media=[
            {
                "stored_path": str(workspace_tmp / "video.mp4"),
                "filename": "video.mp4",
                "media_type": "video",
            }
        ],
        query="driver without seatbelt",
        settings={"fps": 1.0},
        batch_id="batch_1",
        job_id="job_1",
    )

    assert job["status"] == "queued"
    assert store.next_queued_job()["job_id"] == "job_1"

    updated = store.update_job("job_1", status="processing", stage="extracting")

    assert updated["status"] == "processing"
    assert store.get_job("job_1")["stage"] == "extracting"


def test_failed_job_records_error(workspace_tmp):
    store = JobStore(root=workspace_tmp)
    store.create_job(media=[], job_id="job_1")

    failed = store._fail("job_1", "boom")

    assert failed["status"] == "failed"
    assert failed["error"] == "boom"


def test_update_media_statuses_updates_job_media(workspace_tmp):
    store = JobStore(root=workspace_tmp)
    store.create_job(
        media=[
            {
                "stored_path": str(workspace_tmp / "video.mp4"),
                "filename": "video.mp4",
                "media_type": "video",
                "status": "queued",
            }
        ],
        job_id="job_1",
    )

    updated = store.update_media_statuses("job_1", "processing")

    assert updated["media"][0]["status"] == "processing"


def test_zip_vehicle_media_records_are_stored_in_job(workspace_tmp):
    store = JobStore(root=workspace_tmp)
    media = [
        UploadedMedia(
            batch_id="batch_1",
            vehicle_id="Vehicle_A",
            original_relative_path="Vehicle_A/video1.mp4",
            filename="video1.mp4",
            stored_path=str(workspace_tmp / "Vehicle_A" / "video1.mp4"),
            media_type="video",
        ).to_dict(),
        UploadedMedia(
            batch_id="batch_1",
            vehicle_id="Vehicle_B",
            original_relative_path="Vehicle_B/video2.mkv",
            filename="video2.mkv",
            stored_path=str(workspace_tmp / "Vehicle_B" / "video2.mkv"),
            media_type="video",
        ).to_dict(),
    ]

    job = store.create_job(media=media, batch_id="batch_1", job_id="job_zip")

    assert job["batch_id"] == "batch_1"
    assert [item["vehicle_id"] for item in job["media"]] == ["Vehicle_A", "Vehicle_B"]
    assert job["media"][0]["original_relative_path"] == "Vehicle_A/video1.mp4"


def test_auto_worker_subprocess_starts_with_required_env(workspace_tmp, monkeypatch):
    store = JobStore(root=workspace_tmp)
    store.create_job(
        media=[
            {
                "stored_path": str(workspace_tmp / "video.mp4"),
                "filename": "video.mp4",
                "media_type": "video",
            }
        ],
        job_id="job_1",
    )
    captured = {}

    class FakeProcess:
        pid = 12345

    def fake_popen(cmd, **kwargs):
        captured["cmd"] = cmd
        captured["kwargs"] = kwargs
        return FakeProcess()

    monkeypatch.setattr("src.jobs.subprocess.Popen", fake_popen)

    result = store.start_worker_once_subprocess(
        repo_root=workspace_tmp,
        python_executable="python-test",
    )

    assert result["started"] is True
    assert captured["cmd"] == ["python-test", "main.py", "worker", "--once"]
    env = captured["kwargs"]["env"]
    assert env["TORCH_FORCE_NO_WEIGHTS_ONLY_LOAD"] == "1"
    assert env["KMP_DUPLICATE_LIB_OK"] == "TRUE"
    assert env["OMP_NUM_THREADS"] == "1"
    assert env["SAFETRACE_WORKER_LOCK_HELD"] == "1"
    assert store.worker_lock_exists()


def test_auto_worker_does_not_start_when_job_is_processing(workspace_tmp, monkeypatch):
    store = JobStore(root=workspace_tmp)
    store.create_job(
        media=[
            {
                "stored_path": str(workspace_tmp / "video.mp4"),
                "filename": "video.mp4",
                "media_type": "video",
            }
        ],
        job_id="job_1",
    )
    store.update_job("job_1", status="processing")

    def fail_popen(*args, **kwargs):
        raise AssertionError("Popen should not be called")

    monkeypatch.setattr("src.jobs.subprocess.Popen", fail_popen)

    result = store.start_worker_once_subprocess(repo_root=workspace_tmp)

    assert result["started"] is False
    assert "processing" in result["reason"]
