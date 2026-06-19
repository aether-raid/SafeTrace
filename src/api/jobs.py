"""In-process job registry and lazy SafeTrace pipeline execution."""
from __future__ import annotations

import re
import shutil
import threading
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Literal, Optional

from src.config import SETTINGS

from .normalization import normalize_pipeline_results

JobState = Literal["queued", "running", "completed", "failed", "cancelled"]
MEDIA_EXTENSIONS = {
    ".jpg": "image",
    ".jpeg": "image",
    ".png": "image",
    ".bmp": "image",
    ".webp": "image",
    ".mp4": "video",
    ".mov": "video",
    ".avi": "video",
    ".mkv": "video",
    ".webm": "video",
}

_PIPELINE_SETTINGS_LOCK = threading.Lock()


@dataclass
class AnalysisSettings:
    fps: float
    top_k: int
    enable_vlm: bool
    device: str


@dataclass
class JobRecord:
    job_id: str
    status: JobState
    progress: float
    current_step: str
    error: Optional[str]
    query: str
    settings: AnalysisSettings
    original_filename: str
    media_type: str
    size_bytes: int
    job_dir: Path
    upload_path: Path
    output_dir: Path
    result: Optional[Dict] = None
    technical_error: Optional[str] = None
    media_files: Dict[str, Path] = field(default_factory=dict)
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def status_payload(self) -> Dict:
        return {
            "jobId": self.job_id,
            "status": self.status,
            "progress": self.progress,
            "currentStep": self.current_step,
            "error": self.error,
        }


def safe_filename(filename: str) -> str:
    name = Path(filename or "upload.bin").name
    stem = re.sub(r"[^A-Za-z0-9_.-]+", "_", Path(name).stem).strip("._") or "upload"
    suffix = Path(name).suffix.lower()
    return f"{stem}{suffix}"


def media_type_for(filename: str) -> str:
    return MEDIA_EXTENSIONS.get(Path(filename).suffix.lower(), "unknown")


def new_job_id() -> str:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    return f"job_{stamp}_{uuid.uuid4().hex[:8]}"


class JobStore:
    def __init__(self, root_dir: Path | None = None) -> None:
        self.root_dir = Path(root_dir or SETTINGS.data_dir / "api_jobs")
        self.root_dir.mkdir(parents=True, exist_ok=True)
        self._jobs: Dict[str, JobRecord] = {}
        self._lock = threading.Lock()

    def create_job(
        self,
        *,
        filename: str,
        content: bytes,
        query: str,
        settings: AnalysisSettings,
    ) -> JobRecord:
        job_id = new_job_id()
        job_dir = self.root_dir / job_id
        upload_dir = job_dir / "uploads"
        output_dir = job_dir / "media"
        upload_dir.mkdir(parents=True, exist_ok=False)
        output_dir.mkdir(parents=True, exist_ok=True)

        clean_name = safe_filename(filename)
        upload_path = upload_dir / clean_name
        upload_path.write_bytes(content)

        record = JobRecord(
            job_id=job_id,
            status="queued",
            progress=0.0,
            current_step="Queued for analysis",
            error=None,
            query=query,
            settings=settings,
            original_filename=clean_name,
            media_type=media_type_for(clean_name),
            size_bytes=len(content),
            job_dir=job_dir,
            upload_path=upload_path,
            output_dir=output_dir,
        )
        with self._lock:
            self._jobs[job_id] = record
        return record

    def get(self, job_id: str) -> Optional[JobRecord]:
        with self._lock:
            return self._jobs.get(job_id)

    def require(self, job_id: str) -> JobRecord:
        record = self.get(job_id)
        if record is None:
            raise KeyError(job_id)
        return record

    def update_status(
        self,
        job_id: str,
        *,
        status: JobState,
        progress: float,
        current_step: str,
        error: Optional[str] = None,
        technical_error: Optional[str] = None,
    ) -> None:
        with self._lock:
            record = self._jobs[job_id]
            record.status = status
            record.progress = progress
            record.current_step = current_step
            record.error = error
            record.technical_error = technical_error
            record.updated_at = datetime.now(timezone.utc)

    def complete_job(self, job_id: str, result: Dict) -> None:
        with self._lock:
            record = self._jobs[job_id]
            record.result = result
            record.status = "completed"
            record.progress = 1.0
            record.current_step = "Analysis completed"
            record.error = None
            record.updated_at = datetime.now(timezone.utc)

    def register_media_file(self, job_id: str, filename: str, path: Path) -> None:
        with self._lock:
            record = self._jobs[job_id]
            record.media_files[filename] = path

    def delete(self, job_id: str) -> bool:
        with self._lock:
            record = self._jobs.pop(job_id, None)
        if record is None:
            return False
        root = self.root_dir.resolve()
        target = record.job_dir.resolve()
        if target == root or root not in target.parents:
            raise RuntimeError("Refusing to delete job directory outside API job root.")
        shutil.rmtree(target, ignore_errors=True)
        return True


def run_pipeline(
    *,
    upload_path: Path,
    query: str,
    fps: float,
    top_k: int,
    device: str,
    enable_vlm: bool,
):
    """Run the existing SafeTrace pipeline lazily.

    The heavy pipeline import and construction happen only inside this function.
    """
    from src.config import SETTINGS
    from src.pipeline import SafeTracePipeline

    with _PIPELINE_SETTINGS_LOCK:
        old_device = SETTINGS.device
        old_enable_vlm = SETTINGS.enable_vlm
        SETTINGS.device = device
        SETTINGS.enable_vlm = enable_vlm
        try:
            pipeline = SafeTracePipeline()
            return pipeline.run([upload_path], query=query, fps=fps, k=top_k)
        finally:
            SETTINGS.device = old_device
            SETTINGS.enable_vlm = old_enable_vlm


def execute_analysis_job(store: JobStore, job_id: str) -> None:
    record = store.require(job_id)
    store.update_status(
        job_id,
        status="running",
        progress=0.15,
        current_step="Preparing selected media",
    )
    try:
        store.update_status(
            job_id,
            status="running",
            progress=0.35,
            current_step="Running SafeTrace analysis",
        )
        raw_result = run_pipeline(
            upload_path=record.upload_path,
            query=record.query,
            fps=record.settings.fps,
            top_k=record.settings.top_k,
            device=record.settings.device,
            enable_vlm=record.settings.enable_vlm,
        )
        store.update_status(
            job_id,
            status="running",
            progress=0.85,
            current_step="Normalizing evidence report",
        )
        result = normalize_pipeline_results(
            job_id=job_id,
            media_name=record.original_filename,
            media_type=record.media_type,
            media_size_bytes=record.size_bytes,
            query=record.query,
            raw_frames=raw_result,
            media_dir=record.output_dir,
            register_media=lambda filename, path: store.register_media_file(job_id, filename, path),
        )
        store.complete_job(job_id, result)
    except Exception as exc:  # pragma: no cover - exercised through API tests
        store.update_status(
            job_id,
            status="failed",
            progress=1.0,
            current_step="Analysis failed",
            error="Analysis could not be completed. Please try again.",
            technical_error=str(exc),
        )

