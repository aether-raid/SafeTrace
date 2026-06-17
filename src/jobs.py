"""Lightweight file-backed SafeTrace job queue."""
from __future__ import annotations

import json
import logging
import os
import subprocess
import sys
import time
import uuid
from pathlib import Path
from typing import Iterable, Optional

from .config import SETTINGS

logger = logging.getLogger("safetrace.jobs")

TERMINAL_STATUSES = {"completed", "failed"}
REQUIRED_WORKER_ENV = {
    "TORCH_FORCE_NO_WEIGHTS_ONLY_LOAD": "1",
    "KMP_DUPLICATE_LIB_OK": "TRUE",
    "OMP_NUM_THREADS": "1",
}


class JobStore:
    """JSON-file job queue rooted under ``data/jobs`` by default."""

    def __init__(self, root: str | Path | None = None) -> None:
        self.root = Path(root or SETTINGS.jobs_dir)
        self.root.mkdir(parents=True, exist_ok=True)

    def new_job_id(self) -> str:
        return uuid.uuid4().hex[:12]

    def job_dir(self, job_id: str) -> Path:
        return self.root / job_id

    def job_path(self, job_id: str) -> Path:
        return self.job_dir(job_id) / "job.json"

    @property
    def worker_lock_path(self) -> Path:
        return self.root / "worker.lock"

    def create_job(
        self,
        media: Iterable[dict],
        query: str = "",
        settings: Optional[dict] = None,
        batch_id: str | None = None,
        job_id: str | None = None,
    ) -> dict:
        job_id = job_id or self.new_job_id()
        batch_id = batch_id or job_id
        job = {
            "job_id": job_id,
            "batch_id": batch_id,
            "status": "queued",
            "stage": "queued",
            "progress": 0.0,
            "processed_frames": 0,
            "error": None,
            "query": query,
            "settings": settings or {},
            "media": list(media),
            "result_path": None,
            "created_at": time.time(),
            "updated_at": time.time(),
        }
        self._write(job_id, job)
        return job

    def get_job(self, job_id: str) -> dict:
        path = self.job_path(job_id)
        if not path.exists():
            raise FileNotFoundError(f"Job not found: {job_id}")
        return json.loads(path.read_text(encoding="utf-8"))

    def update_job(self, job_id: str, **updates) -> dict:
        job = self.get_job(job_id)
        job.update(updates)
        job["updated_at"] = time.time()
        self._write(job_id, job)
        return job

    def update_media_statuses(self, job_id: str, status: str) -> dict:
        job = self.get_job(job_id)
        media = []
        for item in job.get("media", []):
            updated = dict(item)
            updated["status"] = status
            media.append(updated)
        return self.update_job(job_id, media=media)

    def list_jobs(self) -> list[dict]:
        jobs = []
        for path in self.root.glob("*/job.json"):
            try:
                jobs.append(json.loads(path.read_text(encoding="utf-8")))
            except (OSError, json.JSONDecodeError):
                logger.warning("Ignoring unreadable job file %s", path)
        return sorted(jobs, key=lambda job: job.get("created_at", 0.0), reverse=True)

    def next_queued_job(self) -> dict | None:
        queued = [job for job in self.list_jobs() if job.get("status") == "queued"]
        if not queued:
            return None
        return sorted(queued, key=lambda job: job.get("created_at", 0.0))[0]

    def has_processing_job(self) -> bool:
        return any(job.get("status") == "processing" for job in self.list_jobs())

    def worker_lock_exists(self) -> bool:
        return self.worker_lock_path.exists()

    def acquire_worker_lock(self, owner: str, pid: int | None = None) -> bool:
        payload = {
            "owner": owner,
            "pid": pid,
            "created_at": time.time(),
        }
        try:
            fd = os.open(
                self.worker_lock_path,
                os.O_CREAT | os.O_EXCL | os.O_WRONLY,
                0o644,
            )
        except FileExistsError:
            return False
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(payload, fh, indent=2)
        return True

    def update_worker_lock(self, **updates) -> None:
        payload = {}
        if self.worker_lock_path.exists():
            try:
                payload = json.loads(self.worker_lock_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                payload = {}
        payload.update(updates)
        payload["updated_at"] = time.time()
        self.worker_lock_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    def release_worker_lock(self) -> None:
        try:
            self.worker_lock_path.unlink()
        except FileNotFoundError:
            return

    def start_worker_once_subprocess(
        self,
        repo_root: str | Path | None = None,
        python_executable: str | Path | None = None,
    ) -> dict:
        """Start `python main.py worker --once` in the background if safe."""
        if self.has_processing_job():
            return {"started": False, "reason": "A job is already processing."}
        queued = self.next_queued_job()
        if queued is None:
            return {"started": False, "reason": "No queued jobs to process."}
        if not self.acquire_worker_lock(owner="streamlit-auto-launch"):
            return {"started": False, "reason": "A worker is already starting or running."}

        repo = Path(repo_root or SETTINGS.project_root)
        python_bin = str(python_executable or sys.executable)
        env = os.environ.copy()
        env.update(REQUIRED_WORKER_ENV)
        env["SAFETRACE_WORKER_LOCK_HELD"] = "1"

        cmd = [python_bin, "main.py", "worker", "--once"]
        kwargs = {
            "cwd": str(repo),
            "env": env,
            "stdout": subprocess.DEVNULL,
            "stderr": subprocess.DEVNULL,
        }
        if os.name == "nt" and hasattr(subprocess, "CREATE_NO_WINDOW"):
            kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW
        else:
            kwargs["start_new_session"] = True

        try:
            proc = subprocess.Popen(cmd, **kwargs)
        except Exception as exc:
            self.release_worker_lock()
            return {
                "started": False,
                "error": str(exc),
                "reason": "Worker subprocess failed to start.",
            }

        self.update_worker_lock(owner="streamlit-auto-worker", pid=proc.pid, command=cmd)
        return {"started": True, "pid": proc.pid, "command": cmd}

    def process_next(self) -> dict | None:
        job = self.next_queued_job()
        if not job:
            return None
        return self.process_job(job["job_id"])

    def process_job(self, job_id: str) -> dict:
        from .pipeline import SafeTracePipeline
        from .utils import write_json

        job = self.update_job(
            job_id,
            status="processing",
            stage="initializing",
            progress=0.01,
            error=None,
        )
        job_dir = self.job_dir(job_id)
        output_dir = job_dir / "outputs"
        output_dir.mkdir(parents=True, exist_ok=True)

        try:
            media_items = job.get("media", [])
            if not media_items:
                raise ValueError("Job has no media files to process.")
            job = self.update_media_statuses(job_id, "processing")
            media_items = job.get("media", [])
            current_media = None
            if len(media_items) == 1:
                current_media = media_items[0].get("filename") or media_items[0].get("original_relative_path")
            self.update_job(job_id, current_media=current_media)

            paths = [Path(item["stored_path"]) for item in media_items]
            metadata_map = {}
            for index, item in enumerate(media_items):
                path = Path(item["stored_path"])
                video_id = item.get("video_id") or f"{Path(item['filename']).stem}_{index:03d}"
                metadata_map[str(path.resolve())] = {
                    "batch_id": job.get("batch_id"),
                    "vehicle_id": item.get("vehicle_id"),
                    "video_id": video_id,
                    "original_relative_path": item.get("original_relative_path"),
                    "filename": item.get("filename"),
                    "media_type": item.get("media_type"),
                }

            settings = job.get("settings") or {}
            self.update_job(job_id, stage="extracting_frames", progress=0.05)
            if settings.get("device"):
                SETTINGS.device = str(settings["device"])
                os.environ["SAFETRACE_DEVICE"] = SETTINGS.device
            pipeline = SafeTracePipeline(data_dir=output_dir)
            pipeline.vlm.enabled = bool(settings.get("enable_vlm", SETTINGS.enable_vlm)) and pipeline.vlm._loaded
            records = pipeline.ingest_records(
                paths,
                fps=float(settings.get("fps", SETTINGS.frame_fps)),
                max_frames=int(settings.get("max_frames", SETTINGS.max_frames)),
                media_metadata=metadata_map,
            )

            self.update_job(
                job_id,
                stage="analyzing_frames",
                progress=0.25,
                processed_frames=0,
                total_frames=len(records),
            )

            def progress(done: int, total: int) -> None:
                percent = 0.25 + (0.60 * (done / max(total, 1)))
                self.update_job(
                    job_id,
                    stage="analyzing_frames",
                    progress=round(percent, 4),
                    processed_frames=done,
                    total_frames=total,
                )

            frame_results = pipeline.analyze_frame_records(records, progress_callback=progress)

            self.update_job(job_id, stage="aggregating_results", progress=0.90)
            summaries = pipeline.summarize_timeline(frame_results)

            search_results = []
            query = str(job.get("query") or "").strip()
            if query:
                self.update_job(job_id, stage="running_search", progress=0.94)
                search_results = pipeline.analyze_query(
                    query,
                    k=int(settings.get("top_k", SETTINGS.top_k)),
                )

            completed_media = [dict(item, status="completed") for item in media_items]
            result = {
                "job_id": job_id,
                "batch_id": job.get("batch_id"),
                "status": "completed",
                "summaries": summaries,
                "frame_results": frame_results,
                "search_results": search_results,
                "media": completed_media,
            }
            result_path = output_dir / "results.json"
            write_json(result_path, result)
            job = self.update_media_statuses(job_id, "completed")
            return self.update_job(
                job_id,
                status="completed",
                stage="completed",
                progress=1.0,
                result_path=str(result_path),
                processed_frames=len(records),
                current_media=None,
            )
        except MemoryError as exc:
            return self._fail(job_id, f"Out of memory while processing job: {exc}")
        except RuntimeError as exc:
            message = str(exc)
            if "out of memory" in message.lower() or "cuda" in message.lower():
                return self._fail(job_id, f"Model runtime failure: {message}")
            return self._fail(job_id, message)
        except Exception as exc:
            return self._fail(job_id, str(exc))

    def worker_loop(
        self,
        once: bool = False,
        poll_interval: float = 2.0,
        lock_already_held: bool = False,
    ) -> None:
        acquired = lock_already_held
        if not acquired:
            acquired = self.acquire_worker_lock(owner="cli-worker", pid=os.getpid())
            if not acquired:
                logger.info("Another SafeTrace worker is already running.")
                return
        try:
            self.update_worker_lock(pid=os.getpid(), once=once)
            while True:
                job = self.process_next()
                if job is None:
                    if once:
                        return
                    time.sleep(poll_interval)
                elif once:
                    return
        finally:
            self.release_worker_lock()

    def _fail(self, job_id: str, message: str) -> dict:
        logger.error("Job %s failed: %s", job_id, message)
        try:
            self.update_media_statuses(job_id, "failed")
        except Exception:
            logger.warning("Could not update media status for failed job %s", job_id)
        return self.update_job(
            job_id,
            status="failed",
            stage="failed",
            error=message,
            progress=0.0,
            current_media=None,
        )

    def _write(self, job_id: str, job: dict) -> None:
        job_dir = self.job_dir(job_id)
        job_dir.mkdir(parents=True, exist_ok=True)
        path = self.job_path(job_id)
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(job, indent=2, default=str), encoding="utf-8")
        tmp.replace(path)
