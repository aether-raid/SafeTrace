"""FastAPI app for the local SafeTrace backend."""
from __future__ import annotations

from pathlib import Path
from typing import Optional

from fastapi import BackgroundTasks, Depends, FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, JSONResponse

from src import __version__
from src.config import SETTINGS

from .jobs import AnalysisSettings, JobStore, execute_analysis_job
from .media import resolve_job_media_path
from .schemas import (
    AnalysisResultResponse,
    AnalyzeResponse,
    DeviceMode,
    HealthResponse,
    JobStatusResponse,
    ModelStatus,
    SystemStatusResponse,
)


def _display_path(path: Path) -> str:
    try:
        return str(path.relative_to(SETTINGS.project_root))
    except ValueError:
        return str(path)


def _path_has_contents(path: Path) -> bool:
    if path.is_file():
        return True
    if path.is_dir():
        try:
            return any(path.iterdir())
        except OSError:
            return False
    return False


def _path_status(path: Path, *, optional: bool = False, unavailable_message: Optional[str] = None) -> ModelStatus:
    display = _display_path(path)
    if path.exists() and _path_has_contents(path):
        return ModelStatus(status="ready", path=display)
    if optional:
        return ModelStatus(
            status="unavailable",
            path=display,
            message=unavailable_message or "Optional model unavailable",
        )
    return ModelStatus(
        status="missing",
        path=display,
        message="Required model path is missing",
    )


def _gpu_available() -> bool:
    try:
        import torch

        return bool(torch.cuda.is_available())
    except Exception:
        return False


def _detector_status() -> ModelStatus:
    if SETTINGS.yolo_checkpoint.exists():
        return ModelStatus(status="ready", path=_display_path(SETTINGS.yolo_checkpoint))
    if SETTINGS.yolo_fallback_checkpoint.exists():
        return ModelStatus(
            status="ready",
            path=_display_path(SETTINGS.yolo_fallback_checkpoint),
            message="Using fallback detector checkpoint",
        )
    return ModelStatus(
        status="missing",
        path=_display_path(SETTINGS.yolo_checkpoint),
        message="No YOLO checkpoint found at primary or fallback path",
    )


def get_job_store(request: Request) -> JobStore:
    return request.app.state.job_store


def create_app(job_store: JobStore | None = None) -> FastAPI:
    app = FastAPI(title="SafeTrace Local API", version=__version__)
    app.state.job_store = job_store or JobStore()

    @app.exception_handler(Exception)
    async def unhandled_exception_handler(request: Request, exc: Exception):  # noqa: ARG001
        return JSONResponse(
            status_code=500,
            content={"detail": {"message": "Internal server error"}},
        )

    @app.get("/api/health", response_model=HealthResponse)
    def health() -> HealthResponse:
        return HealthResponse(
            status="ok",
            api="safetrace-local",
            version="dev",
            offline=SETTINGS.offline,
        )

    @app.get("/api/system/status", response_model=SystemStatusResponse)
    def system_status() -> SystemStatusResponse:
        vlm_status = (
            _path_status(SETTINGS.vlm_model_dir, optional=True, unavailable_message="VLM explanations disabled")
            if SETTINGS.enable_vlm
            else ModelStatus(
                status="unavailable",
                path=_display_path(SETTINGS.vlm_model_dir),
                message="VLM explanations disabled",
            )
        )
        return SystemStatusResponse(
            device=SETTINGS.device,
            gpuAvailable=_gpu_available(),
            models={
                "embeddingModel": _path_status(SETTINGS.siglip_model_dir),
                "detector": _detector_status(),
                "mobileSam": _path_status(
                    SETTINGS.mobile_sam_checkpoint,
                    optional=True,
                    unavailable_message="Refinement disabled",
                ),
                "vlm": vlm_status,
            },
        )

    @app.post("/api/analyze", response_model=AnalyzeResponse)
    async def analyze(
        background_tasks: BackgroundTasks,
        file: UploadFile = File(...),
        query: str = Form(...),
        fps: float = Form(1.0),
        topK: int = Form(5),
        enableVlm: bool = Form(False),
        device: DeviceMode = Form("auto"),
        store: JobStore = Depends(get_job_store),
    ) -> AnalyzeResponse:
        if not query.strip():
            raise HTTPException(status_code=400, detail={"message": "Query is required"})
        if fps <= 0:
            raise HTTPException(status_code=400, detail={"message": "fps must be greater than zero"})
        if topK <= 0:
            raise HTTPException(status_code=400, detail={"message": "topK must be greater than zero"})

        content = await file.read()
        if not content:
            raise HTTPException(status_code=400, detail={"message": "Uploaded file is empty"})

        record = store.create_job(
            filename=file.filename or "upload.bin",
            content=content,
            query=query.strip(),
            settings=AnalysisSettings(
                fps=fps,
                top_k=topK,
                enable_vlm=enableVlm,
                device=device,
            ),
        )
        background_tasks.add_task(execute_analysis_job, store, record.job_id)
        return AnalyzeResponse(jobId=record.job_id, status="queued")

    @app.get("/api/jobs/{job_id}", response_model=JobStatusResponse)
    def job_status(job_id: str, store: JobStore = Depends(get_job_store)) -> JobStatusResponse:
        record = store.get(job_id)
        if record is None:
            raise HTTPException(status_code=404, detail={"message": "Job not found"})
        return JobStatusResponse(**record.status_payload())

    @app.get("/api/jobs/{job_id}/result", response_model=AnalysisResultResponse)
    def job_result(job_id: str, store: JobStore = Depends(get_job_store)) -> AnalysisResultResponse:
        record = store.get(job_id)
        if record is None:
            raise HTTPException(status_code=404, detail={"message": "Job not found"})
        if record.status == "failed":
            raise HTTPException(status_code=409, detail={"message": record.error or "Analysis failed"})
        if record.status != "completed" or record.result is None:
            raise HTTPException(status_code=409, detail={"message": "Analysis result is not ready"})
        return AnalysisResultResponse(**record.result)

    @app.get("/api/media/{job_id}/{filename:path}")
    def job_media(job_id: str, filename: str, store: JobStore = Depends(get_job_store)) -> FileResponse:
        record = store.get(job_id)
        if record is None:
            raise HTTPException(status_code=404, detail={"message": "Job not found"})
        path = resolve_job_media_path(record, filename)
        if path is None:
            raise HTTPException(status_code=404, detail={"message": "Media file not found"})
        return FileResponse(path)

    @app.get("/api/reports/{job_id}/technical-json")
    def technical_json(job_id: str, store: JobStore = Depends(get_job_store)):
        record = store.get(job_id)
        if record is None:
            raise HTTPException(status_code=404, detail={"message": "Job not found"})
        if record.status != "completed" or record.result is None:
            raise HTTPException(status_code=409, detail={"message": "Technical report is not ready"})
        return {
            **record.result,
            "technicalDetails": {
                **(record.result.get("technicalDetails") or {}),
                "job": record.status_payload(),
            },
        }

    @app.delete("/api/jobs/{job_id}")
    def delete_job(job_id: str, store: JobStore = Depends(get_job_store)):
        if not store.delete(job_id):
            raise HTTPException(status_code=404, detail={"message": "Job not found"})
        return {"jobId": job_id, "status": "deleted"}

    return app


app = create_app()
