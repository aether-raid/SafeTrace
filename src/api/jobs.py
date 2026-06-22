"""Job registry, manifest persistence, and lazy SafeTrace execution."""
from __future__ import annotations

import json
import os
import re
import shutil
import threading
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, Literal, Optional

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
TERMINAL_STATES = {"completed", "failed", "cancelled"}
ACTIVE_STATES = {"queued", "running"}
MANIFEST_FILENAME = "manifest.json"
RESULT_FILENAME = "result.json"
LOCK_FILENAME = "execution.lock"

_PIPELINE_SETTINGS_LOCK = threading.Lock()
_EXECUTION_SEMAPHORE = threading.BoundedSemaphore(max(int(SETTINGS.worker_concurrency), 1))


class UploadValidationError(ValueError):
    def __init__(self, message: str, *, status_code: int = 400) -> None:
        super().__init__(message)
        self.message = message
        self.status_code = status_code


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
    result: Optional[Dict[str, Any]] = None
    result_path: Optional[Path] = None
    technical_error: Optional[str] = None
    error_type: Optional[str] = None
    media_files: Dict[str, Path] = field(default_factory=dict)
    metrics: Dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    started_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None

    @property
    def manifest_path(self) -> Path:
        return self.job_dir / MANIFEST_FILENAME

    def status_payload(self) -> Dict[str, Any]:
        return {
            "jobId": self.job_id,
            "status": self.status,
            "progress": self.progress,
            "currentStep": self.current_step,
            "error": self.error,
            "metrics": self.metrics,
        }


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _to_iso(value: Optional[datetime]) -> Optional[str]:
    return value.astimezone(timezone.utc).isoformat() if value else None


def _parse_datetime(value: Any) -> Optional[datetime]:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _safe_relative_path(path: Path, root: Path) -> Optional[str]:
    try:
        return str(path.resolve().relative_to(root.resolve())).replace("\\", "/")
    except ValueError:
        return None


def _resolve_manifest_path(job_dir: Path, raw_path: Any, default: Path) -> Path:
    if not raw_path:
        return default
    candidate = (job_dir / str(raw_path)).resolve()
    root = job_dir.resolve()
    if candidate == root or root in candidate.parents:
        return candidate
    return default


def _atomic_write_json(path: Path, payload: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    temporary.replace(path)


def safe_filename(filename: str) -> str:
    name = Path(filename or "upload.bin").name
    stem = re.sub(r"[^A-Za-z0-9_.-]+", "_", Path(name).stem).strip("._") or "upload"
    suffix = Path(name).suffix.lower()
    return f"{stem}{suffix}"


def media_type_for(filename: str) -> str:
    return MEDIA_EXTENSIONS.get(Path(filename).suffix.lower(), "unknown")


def allowed_upload_extensions() -> list[str]:
    return sorted(MEDIA_EXTENSIONS)


def max_upload_bytes() -> int:
    return max(int(float(SETTINGS.max_upload_mb) * 1024 * 1024), 1)


def validate_upload_filename(filename: str) -> str:
    clean_name = safe_filename(filename)
    if media_type_for(clean_name) == "unknown":
        allowed = ", ".join(allowed_upload_extensions())
        raise UploadValidationError(
            f"Unsupported upload type. Allowed extensions: {allowed}",
            status_code=415,
        )
    return clean_name


def validate_upload_size(size_bytes: int, *, limit_bytes: Optional[int] = None) -> None:
    limit = limit_bytes if limit_bytes is not None else max_upload_bytes()
    if size_bytes > limit:
        max_mb = limit / (1024 * 1024)
        raise UploadValidationError(
            f"Uploaded file is too large. Maximum size is {max_mb:.1f} MB.",
            status_code=413,
        )


def new_job_id() -> str:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    return f"job_{stamp}_{uuid.uuid4().hex[:8]}"


def _is_safe_job_id(job_id: str) -> bool:
    return bool(re.fullmatch(r"job_[A-Za-z0-9_.-]+", job_id or ""))


def _settings_to_manifest(settings: AnalysisSettings) -> Dict[str, Any]:
    return {
        "fps": settings.fps,
        "topK": settings.top_k,
        "enableVlm": settings.enable_vlm,
        "device": settings.device,
    }


def _settings_from_manifest(payload: Dict[str, Any]) -> AnalysisSettings:
    return AnalysisSettings(
        fps=float(payload.get("fps") or 1.0),
        top_k=int(payload.get("topK") or payload.get("top_k") or 5),
        enable_vlm=bool(payload.get("enableVlm") or payload.get("enable_vlm") or False),
        device=str(payload.get("device") or "auto"),
    )


class JobStore:
    def __init__(self, root_dir: Path | None = None) -> None:
        self.root_dir = Path(root_dir or SETTINGS.data_dir / "api_jobs")
        self.root_dir.mkdir(parents=True, exist_ok=True)
        self._jobs: Dict[str, JobRecord] = {}
        self._lock = threading.RLock()
        self.recover_jobs()

    def create_job(
        self,
        *,
        filename: str,
        content: bytes,
        query: str,
        settings: AnalysisSettings,
    ) -> JobRecord:
        clean_name = validate_upload_filename(filename)
        validate_upload_size(len(content))

        job_id = new_job_id()
        job_dir = self.root_dir / job_id
        upload_dir = job_dir / "uploads"
        output_dir = job_dir / "media"
        upload_dir.mkdir(parents=True, exist_ok=False)
        output_dir.mkdir(parents=True, exist_ok=True)

        upload_path = upload_dir / clean_name
        upload_path.write_bytes(content)

        now = _utc_now()
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
            created_at=now,
            updated_at=now,
        )
        self._refresh_metrics(record)
        with self._lock:
            self._jobs[job_id] = record
            self.persist_job(record)
        return record

    def get(self, job_id: str) -> Optional[JobRecord]:
        with self._lock:
            record = self._jobs.get(job_id)
            if record is None:
                record = self.load_job(job_id)
                if record is not None:
                    self._jobs[job_id] = record
            if record is not None and self._is_stale_active(record):
                self._mark_interrupted(record)
            return record

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
        error_type: Optional[str] = None,
    ) -> None:
        with self._lock:
            record = self._jobs[job_id]
            now = _utc_now()
            if status == "running" and record.started_at is None:
                record.started_at = now
            if status in TERMINAL_STATES and record.finished_at is None:
                record.finished_at = now
            record.status = status
            record.progress = progress
            record.current_step = current_step
            record.error = error
            record.technical_error = technical_error
            record.error_type = error_type
            record.updated_at = now
            self._refresh_metrics(record)
            self.persist_job(record)

    def complete_job(self, job_id: str, result: Dict[str, Any]) -> None:
        with self._lock:
            record = self._jobs[job_id]
            now = _utc_now()
            record.status = "completed"
            record.progress = 1.0
            record.current_step = "Analysis completed"
            record.error = None
            record.error_type = None
            record.finished_at = now
            record.updated_at = now
            self._refresh_metrics(record)

            normalized = dict(result)
            technical_details = dict(normalized.get("technicalDetails") or {})
            technical_details["jobMetrics"] = dict(record.metrics)
            normalized["technicalDetails"] = technical_details
            record.result = normalized
            record.result_path = record.job_dir / RESULT_FILENAME
            self.persist_job(record)

    def register_media_file(self, job_id: str, filename: str, path: Path) -> None:
        with self._lock:
            record = self._jobs[job_id]
            record.media_files[filename] = path
            record.updated_at = _utc_now()
            self.persist_job(record)

    def acquire_execution_lock(self, job_id: str) -> bool:
        record = self.require(job_id)
        lock_path = record.job_dir / LOCK_FILENAME
        try:
            descriptor = os.open(str(lock_path), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        except FileExistsError:
            return False
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            handle.write(_to_iso(_utc_now()) or "")
        return True

    def release_execution_lock(self, job_id: str) -> None:
        record = self.get(job_id)
        if record is None:
            return
        lock_path = record.job_dir / LOCK_FILENAME
        try:
            lock_path.unlink()
        except FileNotFoundError:
            return

    def delete(self, job_id: str) -> bool:
        with self._lock:
            record = self.get(job_id)
            if record is None:
                return False
            self._jobs.pop(job_id, None)
        self._delete_record_dir(record)
        return True

    def cleanup_expired_jobs(self, *, retention_hours: Optional[float] = None) -> list[str]:
        retention = timedelta(
            hours=float(SETTINGS.job_retention_hours if retention_hours is None else retention_hours)
        )
        removed: list[str] = []
        now = _utc_now()
        with self._lock:
            self.recover_jobs()
            for record in list(self._jobs.values()):
                if self._is_stale_active(record):
                    self._mark_interrupted(record)
                if record.status not in TERMINAL_STATES:
                    continue
                age_anchor = record.finished_at or record.updated_at or record.created_at
                if now - age_anchor < retention:
                    continue
                if not self._is_safe_job_dir(record.job_dir):
                    continue
                self._jobs.pop(record.job_id, None)
                self._delete_record_dir(record)
                removed.append(record.job_id)
        return removed

    def recover_jobs(self) -> list[str]:
        recovered: list[str] = []
        with self._lock:
            for job_dir in self.root_dir.iterdir():
                if not job_dir.is_dir():
                    continue
                manifest = job_dir / MANIFEST_FILENAME
                if not manifest.exists():
                    continue
                record = self._load_manifest(manifest)
                if record is None:
                    continue
                self._jobs[record.job_id] = record
                recovered.append(record.job_id)
            self.mark_stale_running_jobs()
        return recovered

    def mark_stale_running_jobs(self) -> list[str]:
        interrupted: list[str] = []
        with self._lock:
            for record in list(self._jobs.values()):
                if self._is_stale_active(record):
                    self._mark_interrupted(record)
                    interrupted.append(record.job_id)
        return interrupted

    def status_counts(self, *, include_disk: bool = False) -> Dict[str, int]:
        with self._lock:
            if include_disk:
                self.recover_jobs()
            counts: Dict[str, int] = {}
            for record in self._jobs.values():
                counts[record.status] = counts.get(record.status, 0) + 1
            return counts

    def persist_job(self, record: JobRecord) -> None:
        if record.result is not None:
            result_path = record.result_path or (record.job_dir / RESULT_FILENAME)
            _atomic_write_json(result_path, record.result)
            record.result_path = result_path

        media_files = {}
        for filename, path in record.media_files.items():
            relative = _safe_relative_path(path, record.job_dir)
            if relative is not None:
                media_files[filename] = relative

        result_path = _safe_relative_path(record.result_path, record.job_dir) if record.result_path else None
        manifest = {
            "jobId": record.job_id,
            "status": record.status,
            "progress": record.progress,
            "currentStep": record.current_step,
            "error": record.error,
            "technicalError": record.technical_error,
            "errorType": record.error_type,
            "createdAt": _to_iso(record.created_at),
            "updatedAt": _to_iso(record.updated_at),
            "startedAt": _to_iso(record.started_at),
            "finishedAt": _to_iso(record.finished_at),
            "query": record.query,
            "settings": _settings_to_manifest(record.settings),
            "input": {
                "originalFilename": record.original_filename,
                "uploadPath": _safe_relative_path(record.upload_path, record.job_dir),
                "mediaType": record.media_type,
                "sizeBytes": record.size_bytes,
            },
            "output": {
                "mediaDir": _safe_relative_path(record.output_dir, record.job_dir),
                "resultPath": result_path,
                "mediaFiles": media_files,
            },
            "metrics": record.metrics,
        }
        _atomic_write_json(record.manifest_path, manifest)

    def load_job(self, job_id: str) -> Optional[JobRecord]:
        if not _is_safe_job_id(job_id):
            return None
        return self._load_manifest(self.root_dir / job_id / MANIFEST_FILENAME)

    def _load_manifest(self, manifest_path: Path) -> Optional[JobRecord]:
        root = self.root_dir.resolve()
        job_dir = manifest_path.parent.resolve()
        if job_dir == root or root not in job_dir.parents:
            return None
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None

        job_id = str(manifest.get("jobId") or job_dir.name)
        if not _is_safe_job_id(job_id):
            return None

        input_meta = dict(manifest.get("input") or {})
        output_meta = dict(manifest.get("output") or {})
        clean_name = safe_filename(str(input_meta.get("originalFilename") or "upload.bin"))
        upload_path = _resolve_manifest_path(job_dir, input_meta.get("uploadPath"), job_dir / "uploads" / clean_name)
        output_dir = _resolve_manifest_path(job_dir, output_meta.get("mediaDir"), job_dir / "media")

        result_path = None
        result = None
        raw_result_path = output_meta.get("resultPath")
        if raw_result_path:
            result_path = _resolve_manifest_path(job_dir, raw_result_path, job_dir / RESULT_FILENAME)
            if result_path.exists():
                try:
                    result = json.loads(result_path.read_text(encoding="utf-8"))
                except (OSError, json.JSONDecodeError):
                    result = None

        media_files: Dict[str, Path] = {}
        for filename, raw_path in dict(output_meta.get("mediaFiles") or {}).items():
            clean_media_name = Path(str(filename)).name
            media_files[clean_media_name] = _resolve_manifest_path(job_dir, raw_path, output_dir / clean_media_name)

        status = str(manifest.get("status") or "failed")
        if status not in {"queued", "running", "completed", "failed", "cancelled"}:
            status = "failed"

        record = JobRecord(
            job_id=job_id,
            status=status,  # type: ignore[arg-type]
            progress=float(manifest.get("progress") or 0.0),
            current_step=str(manifest.get("currentStep") or "Recovered job"),
            error=manifest.get("error"),
            query=str(manifest.get("query") or ""),
            settings=_settings_from_manifest(dict(manifest.get("settings") or {})),
            original_filename=clean_name,
            media_type=str(input_meta.get("mediaType") or media_type_for(clean_name)),
            size_bytes=int(input_meta.get("sizeBytes") or 0),
            job_dir=job_dir,
            upload_path=upload_path,
            output_dir=output_dir,
            result=result,
            result_path=result_path,
            technical_error=manifest.get("technicalError"),
            error_type=manifest.get("errorType"),
            media_files=media_files,
            metrics=dict(manifest.get("metrics") or {}),
            created_at=_parse_datetime(manifest.get("createdAt")) or _utc_now(),
            updated_at=_parse_datetime(manifest.get("updatedAt")) or _utc_now(),
            started_at=_parse_datetime(manifest.get("startedAt")),
            finished_at=_parse_datetime(manifest.get("finishedAt")),
        )
        self._refresh_metrics(record)
        return record

    def _refresh_metrics(self, record: JobRecord) -> None:
        metrics = dict(record.metrics)
        metrics.update(
            {
                "queuedAt": _to_iso(record.created_at),
                "startedAt": _to_iso(record.started_at),
                "finishedAt": _to_iso(record.finished_at),
                "inputSizeBytes": record.size_bytes,
                "inputMediaType": record.media_type,
                "inputExtension": Path(record.original_filename).suffix.lower(),
                "statusOutcome": record.status,
            }
        )
        if record.finished_at:
            started_anchor = record.started_at or record.created_at
            metrics["totalWallClockSeconds"] = max(
                (record.finished_at - started_anchor).total_seconds(),
                0.0,
            )
        elif record.created_at and record.updated_at:
            metrics["elapsedWallClockSeconds"] = max(
                (record.updated_at - record.created_at).total_seconds(),
                0.0,
            )
        if record.error_type:
            metrics["errorType"] = record.error_type
        if record.error:
            metrics["errorMessage"] = record.error
        record.metrics = metrics

    def _is_safe_job_dir(self, job_dir: Path) -> bool:
        root = self.root_dir.resolve()
        target = job_dir.resolve()
        return target != root and root in target.parents

    def _delete_record_dir(self, record: JobRecord) -> None:
        if not self._is_safe_job_dir(record.job_dir):
            raise RuntimeError("Refusing to delete job directory outside API job root.")
        shutil.rmtree(record.job_dir, ignore_errors=True)

    def _is_stale_active(self, record: JobRecord) -> bool:
        if record.status not in ACTIVE_STATES:
            return False
        cutoff = _utc_now() - timedelta(minutes=float(SETTINGS.stale_running_minutes))
        return record.updated_at < cutoff

    def _mark_interrupted(self, record: JobRecord) -> None:
        lock_path = record.job_dir / LOCK_FILENAME
        try:
            lock_path.unlink()
        except FileNotFoundError:
            pass
        record.status = "failed"
        record.progress = 1.0
        record.current_step = "Analysis interrupted"
        record.error = "Job interrupted by backend restart."
        record.error_type = "InterruptedJob"
        record.finished_at = _utc_now()
        record.updated_at = record.finished_at
        self._refresh_metrics(record)
        self.persist_job(record)


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
    try:
        record = store.require(job_id)
    except KeyError:
        return
    if record.status in TERMINAL_STATES:
        return
    if not store.acquire_execution_lock(job_id):
        return

    try:
        with _EXECUTION_SEMAPHORE:
            record = store.require(job_id)
            if record.status in TERMINAL_STATES:
                return
            started = time.perf_counter()
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
                result.setdefault("technicalDetails", {})["pipelineWallClockSeconds"] = time.perf_counter() - started
                store.complete_job(job_id, result)
            except Exception as exc:  # pragma: no cover - exercised through API tests
                store.update_status(
                    job_id,
                    status="failed",
                    progress=1.0,
                    current_step="Analysis failed",
                    error="Analysis could not be completed. Please try again.",
                    technical_error=str(exc),
                    error_type=type(exc).__name__,
                )
    finally:
        store.release_execution_lock(job_id)
