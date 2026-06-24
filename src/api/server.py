"""FastAPI app for the local SafeTrace backend."""
from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Optional

from fastapi import BackgroundTasks, Depends, FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from src import __version__
from src.chat_service import (
    ChatDisabledError,
    ChatProviderUnavailableError,
    answer_chat,
    chat_status_payload,
    warmup_chat_provider,
)
from src.config import SETTINGS

from .batches import BatchStore, BatchValidationError
from .jobs import (
    AnalysisSettings,
    JobStore,
    UploadValidationError,
    execute_analysis_job,
    max_upload_bytes,
    validate_upload_filename,
    validate_upload_size,
)
from .media import resolve_job_media_path
from .schemas import (
    AnalysisResultResponse,
    AnalyzeResponse,
    BatchResponse,
    ChatRequest,
    ChatResponse,
    ChatStatusResponse,
    DeviceMode,
    HealthResponse,
    JobStatusResponse,
    ModelStatus,
    SystemStatusResponse,
)


LOCAL_FRONTEND_ORIGINS = (
    "http://127.0.0.1:5173",
    "http://localhost:5173",
)


def _split_origins(raw: str) -> tuple[str, ...]:
    return tuple(part.strip().rstrip("/") for part in raw.split(",") if part.strip())


def _normalize_origin(origin: str | None) -> str:
    return (origin or "").strip().rstrip("/")


def _cors_allowed_origins() -> list[str]:
    origins = [
        *LOCAL_FRONTEND_ORIGINS,
        *getattr(SETTINGS, "allowed_origins", ()),
        *_split_origins(os.environ.get("SAFETRACE_ALLOWED_ORIGINS", "")),
    ]
    return list(dict.fromkeys(_normalize_origin(origin) for origin in origins if _normalize_origin(origin)))


def _is_cors_origin_allowed(origin: str | None) -> bool:
    normalized = _normalize_origin(origin)
    return bool(normalized and normalized in set(_cors_allowed_origins()))


def _configure_cors(app: FastAPI) -> None:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=_cors_allowed_origins(),
        allow_credentials=False,
        allow_methods=["GET", "POST", "DELETE", "OPTIONS"],
        allow_headers=["*"],
        max_age=600,
    )

    @app.middleware("http")
    async def private_network_access_header(request: Request, call_next):
        response = await call_next(request)
        requested_private_network = (
            request.method == "OPTIONS"
            and request.headers.get("access-control-request-private-network", "").lower() == "true"
        )
        if requested_private_network and _is_cors_origin_allowed(request.headers.get("origin")):
            response.headers["Access-Control-Allow-Private-Network"] = "true"
        return response


def _display_path(path: Path) -> str:
    try:
        return str(path.relative_to(SETTINGS.project_root))
    except ValueError:
        return str(path)


def _resolve_configured_path(path: Path) -> Path:
    if path.is_absolute():
        return path
    cwd_candidate = (Path.cwd() / path).resolve()
    if cwd_candidate.exists():
        return cwd_candidate
    return (SETTINGS.project_root / path).resolve()


def _frontend_dist_path() -> Path:
    return _resolve_configured_path(Path(SETTINGS.frontend_dist))


def _frontend_status_payload() -> dict:
    dist = _frontend_dist_path()
    index = dist / "index.html"
    return {
        "serveFrontend": bool(SETTINGS.serve_frontend),
        "distPath": _display_path(dist),
        "distExists": dist.is_dir(),
        "indexExists": index.is_file(),
        "message": (
            "Frontend static serving is enabled."
            if SETTINGS.serve_frontend and index.is_file()
            else "Frontend static serving is disabled or the dist index is missing."
        ),
    }


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


def _model_status_payload(status: ModelStatus) -> dict:
    return {
        "status": status.status,
        "path": status.path,
        "message": status.message,
    }


def _runtime_check(
    status: str,
    message: str,
    *,
    path: Optional[str] = None,
    action_hint: Optional[str] = None,
    details: Optional[dict] = None,
) -> dict:
    payload = {
        "status": status,
        "message": message,
        "path": path,
        "actionHint": action_hint,
    }
    if details:
        payload["details"] = details
    return payload


def _model_preflight_check(label: str, status: ModelStatus, *, optional: bool = False) -> dict:
    if status.status == "ready":
        return _runtime_check("ready", f"{label} ready", path=status.path)
    if status.status == "missing":
        return _runtime_check(
            "missing",
            status.message or f"{label} missing",
            path=status.path,
            action_hint=f"Place the required {label} asset at the configured path.",
        )
    return _runtime_check(
        "unavailable",
        status.message or f"{label} unavailable",
        path=status.path,
        action_hint=None if optional else f"Check the configured {label} path.",
    )


def _openmp_status() -> dict:
    kmp_value = os.environ.get("KMP_DUPLICATE_LIB_OK")
    omp_value = os.environ.get("OMP_NUM_THREADS")
    kmp_enabled = str(kmp_value or "").strip().upper() == "TRUE"
    status = "ready" if kmp_enabled else "warning"
    return {
        "status": status,
        "kmpDuplicateLibOk": kmp_enabled,
        "rawKmpDuplicateLibOk": kmp_value,
        "ompNumThreads": omp_value,
        "message": (
            "OpenMP duplicate runtime workaround is enabled."
            if kmp_enabled
            else "OpenMP duplicate runtime workaround is not set for this process."
        ),
        "actionHint": None if kmp_enabled else "Set KMP_DUPLICATE_LIB_OK=TRUE before launching on Windows.",
    }


def _assistant_preflight_check(chat: dict) -> dict:
    state = str(chat.get("state") or "unavailable")
    message = str(chat.get("message") or chat.get("reason") or "SafeTrace Assistant status unknown.")
    return _runtime_check(state, message, action_hint=chat.get("action_hint"), details={"provider": chat.get("provider")})


def _assistant_model_check(chat: dict) -> dict:
    provider = str(chat.get("provider") or "unknown")
    model_path = chat.get("model_path")
    model_exists = chat.get("model_exists")
    if provider != "packaged_llamacpp":
        return _runtime_check(
            "unavailable",
            f"Assistant model file check is not applicable for provider {provider}.",
            path=model_path,
        )
    if model_exists is True:
        return _runtime_check("ready", "Assistant model found", path=model_path)
    if model_exists is False:
        return _runtime_check(
            "missing",
            "Assistant model file is missing.",
            path=model_path,
            action_hint=chat.get("action_hint"),
        )
    return _runtime_check("unavailable", "Assistant model file status unknown.", path=model_path)


def _assistant_runtime_check(chat: dict) -> dict:
    provider = str(chat.get("provider") or "unknown")
    runtime_available = chat.get("runtime_available")
    if provider != "packaged_llamacpp":
        return _runtime_check(
            "unavailable",
            f"llama-cpp runtime check is not applicable for provider {provider}.",
        )
    if runtime_available is True:
        return _runtime_check("ready", "Assistant runtime installed")
    if runtime_available is False:
        return _runtime_check(
            "missing",
            "Assistant runtime is missing.",
            action_hint=chat.get("action_hint"),
        )
    return _runtime_check("unavailable", "Assistant runtime status unknown.")


def _preflight_payload(*, models: dict[str, ModelStatus], chat: dict, openmp: dict) -> dict:
    checks = {
        "backend": _runtime_check("ready", "SafeTrace backend is responding."),
        "openmp": _runtime_check(
            openmp["status"],
            openmp["message"],
            action_hint=openmp.get("actionHint"),
            details={
                "kmpDuplicateLibOk": openmp.get("kmpDuplicateLibOk"),
                "ompNumThreads": openmp.get("ompNumThreads"),
            },
        ),
        "embeddingModel": _model_preflight_check("embedding model", models["embeddingModel"]),
        "detector": _model_preflight_check("detector", models["detector"]),
        "mobileSam": _model_preflight_check("MobileSAM", models["mobileSam"], optional=True),
        "vlm": _model_preflight_check("VLM", models["vlm"], optional=True),
        "assistant": _assistant_preflight_check(chat),
        "assistantModel": _assistant_model_check(chat),
        "assistantRuntime": _assistant_runtime_check(chat),
    }
    ready = sum(1 for check in checks.values() if check["status"] in {"ready", "available"})
    warnings = len(checks) - ready
    return {"checks": checks, "summary": {"ready": ready, "warnings": warnings}}


def _runtime_payload(
    *,
    store: "JobStore",
    models: dict[str, ModelStatus],
    gpu_available: bool,
    chat: dict,
    openmp: dict,
) -> dict:
    return {
        "backend": {
            "status": "ready",
            "api": "safetrace-local",
            "version": "dev",
            "offline": SETTINGS.offline,
        },
        "python": {
            "executable": sys.executable,
            "version": sys.version.split()[0],
        },
        "workingDirectory": str(Path.cwd()),
        "device": {
            "configured": SETTINGS.device,
            "gpuAvailable": gpu_available,
        },
        "models": {key: _model_status_payload(value) for key, value in models.items()},
        "chat": chat,
        "openmp": openmp,
        "frontend": _frontend_status_payload(),
        "uploadLimits": {
            "maxUploadMb": SETTINGS.max_upload_mb,
            "maxVideoDurationSeconds": SETTINGS.max_video_duration_seconds,
            "maxSampledFrames": SETTINGS.max_frames,
        },
        "batchLimits": {
            "bulkMaxFiles": SETTINGS.bulk_max_files,
            "bulkMaxUncompressedMb": SETTINGS.bulk_max_uncompressed_mb,
            "workerConcurrency": SETTINGS.worker_concurrency,
        },
        "jobStorePath": _display_path(store.root_dir),
    }


def get_job_store(request: Request) -> JobStore:
    return request.app.state.job_store


def get_batch_store(request: Request) -> BatchStore:
    return request.app.state.batch_store


def _configure_frontend_static(app: FastAPI) -> None:
    if not bool(SETTINGS.serve_frontend):
        return
    dist = _frontend_dist_path()
    index = dist / "index.html"
    if not index.is_file():
        return
    assets = dist / "assets"
    if assets.is_dir():
        app.mount("/assets", StaticFiles(directory=assets), name="frontend-assets")

    @app.get("/", include_in_schema=False)
    def frontend_index() -> FileResponse:
        return FileResponse(index)

    @app.get("/{frontend_path:path}", include_in_schema=False)
    def frontend_fallback(frontend_path: str) -> FileResponse:
        if frontend_path.startswith("api/"):
            raise HTTPException(status_code=404, detail={"message": "API route not found"})
        candidate = (dist / frontend_path).resolve()
        try:
            candidate.relative_to(dist.resolve())
        except ValueError:
            return FileResponse(index)
        if candidate.is_file():
            return FileResponse(candidate)
        return FileResponse(index)


def _upload_http_error(exc: UploadValidationError) -> HTTPException:
    return HTTPException(status_code=exc.status_code, detail={"message": exc.message})


def _batch_http_error(exc: BatchValidationError) -> HTTPException:
    return HTTPException(status_code=exc.status_code, detail={"message": exc.message})


async def _read_upload_content(file: UploadFile, *, limit: Optional[int] = None) -> bytes:
    byte_limit = limit if limit is not None else max_upload_bytes()
    known_size = getattr(file, "size", None)
    if known_size is not None:
        try:
            validate_upload_size(int(known_size), limit_bytes=byte_limit)
        except UploadValidationError as exc:
            raise _upload_http_error(exc) from exc

    chunks = []
    total = 0
    while True:
        chunk = await file.read(1024 * 1024)
        if not chunk:
            break
        total += len(chunk)
        try:
            validate_upload_size(total, limit_bytes=byte_limit)
        except UploadValidationError as exc:
            raise _upload_http_error(exc) from exc
        chunks.append(chunk)
    return b"".join(chunks)


def create_app(job_store: JobStore | None = None, batch_store: BatchStore | None = None) -> FastAPI:
    app = FastAPI(title="SafeTrace Local API", version=__version__)
    app.state.job_store = job_store or JobStore()
    app.state.batch_store = batch_store or BatchStore()
    _configure_cors(app)

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
    def system_status(store: JobStore = Depends(get_job_store)) -> SystemStatusResponse:
        gpu_available = _gpu_available()
        vlm_status = (
            _path_status(SETTINGS.vlm_model_dir, optional=True, unavailable_message="VLM explanations disabled")
            if SETTINGS.enable_vlm
            else ModelStatus(
                status="unavailable",
                path=_display_path(SETTINGS.vlm_model_dir),
                message="VLM explanations disabled",
            )
        )
        models = {
            "embeddingModel": _path_status(SETTINGS.siglip_model_dir),
            "detector": _detector_status(),
            "mobileSam": _path_status(
                SETTINGS.mobile_sam_checkpoint,
                optional=True,
                unavailable_message="Refinement disabled",
            ),
            "vlm": vlm_status,
        }
        limits = {
            "maxUploadMb": SETTINGS.max_upload_mb,
            "bulkMaxFiles": SETTINGS.bulk_max_files,
            "bulkMaxUncompressedMb": SETTINGS.bulk_max_uncompressed_mb,
            "maxVideoDurationSeconds": SETTINGS.max_video_duration_seconds,
            "maxVideoDurationUnlimited": SETTINGS.max_video_duration_seconds <= 0,
            "maxVideoDurationMessage": (
                "No explicit video duration cap is enforced; sampled frames remain bounded."
                if SETTINGS.max_video_duration_seconds <= 0
                else "Video duration cap is enforced during frame extraction."
            ),
            "maxSampledFrames": SETTINGS.max_frames,
            "embeddingBatchSize": SETTINGS.embedding_batch_size,
            "embeddingWindowSize": SETTINGS.embedding_window_size,
            "embeddingWindowStride": SETTINGS.embedding_window_stride,
            "embeddingPoolingStrategy": SETTINGS.embedding_pooling_strategy,
            "workerConcurrency": SETTINGS.worker_concurrency,
            "jobRetentionHours": SETTINGS.job_retention_hours,
            "staleRunningMinutes": SETTINGS.stale_running_minutes,
        }
        chat = chat_status_payload(allow_model_load=False)
        openmp = _openmp_status()
        return SystemStatusResponse(
            app_version=__version__,
            backend_version=__version__,
            build_mode=os.environ.get("SAFETRACE_BUILD_MODE", "development"),
            runtime_layout=os.environ.get("SAFETRACE_RUNTIME_LAYOUT", "source"),
            device=SETTINGS.device,
            gpuAvailable=gpu_available,
            models=models,
            limits=limits,
            queue={
                "statusCounts": store.status_counts(),
                "activeStates": ["queued", "running"],
                "terminalStates": ["completed", "failed", "cancelled"],
            },
            runtime=_runtime_payload(
                store=store,
                models=models,
                gpu_available=gpu_available,
                chat=chat,
                openmp=openmp,
            ),
            preflight=_preflight_payload(models=models, chat=chat, openmp=openmp),
        )

    @app.get("/api/chat/status", response_model=ChatStatusResponse)
    def chat_status() -> ChatStatusResponse:
        return ChatStatusResponse(**chat_status_payload())

    @app.post("/api/chat/warmup", response_model=ChatStatusResponse)
    def chat_warmup() -> ChatStatusResponse:
        try:
            return ChatStatusResponse(**warmup_chat_provider())
        except ChatDisabledError as exc:
            raise HTTPException(status_code=503, detail={"message": str(exc)}) from exc
        except ChatProviderUnavailableError as exc:
            raise HTTPException(status_code=503, detail={"message": str(exc)}) from exc

    @app.post("/api/chat", response_model=ChatResponse)
    def chat(
        request: ChatRequest,
        store: JobStore = Depends(get_job_store),
        batches: BatchStore = Depends(get_batch_store),
    ) -> ChatResponse:
        if not request.message.strip():
            raise HTTPException(status_code=400, detail={"message": "Message is required"})
        try:
            payload = answer_chat(
                message=request.message,
                job_store=store,
                batch_store=batches,
                job_id=request.job_id,
                batch_id=request.batch_id,
                include_current_result=request.include_current_result,
            )
        except ChatDisabledError as exc:
            raise HTTPException(status_code=503, detail={"message": str(exc)}) from exc
        except ChatProviderUnavailableError as exc:
            raise HTTPException(status_code=503, detail={"message": str(exc)}) from exc
        return ChatResponse(**payload)

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

        try:
            clean_filename = validate_upload_filename(file.filename or "upload.bin")
        except UploadValidationError as exc:
            raise _upload_http_error(exc) from exc

        content = await _read_upload_content(file)
        if not content:
            raise HTTPException(status_code=400, detail={"message": "Uploaded file is empty"})

        record = store.create_job(
            filename=clean_filename,
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

    @app.post("/api/batches/analyze", response_model=BatchResponse)
    async def analyze_batch(
        background_tasks: BackgroundTasks,
        files: list[UploadFile] = File(...),
        query: str = Form(...),
        fps: float = Form(1.0),
        topK: int = Form(5),
        enableVlm: bool = Form(False),
        device: DeviceMode = Form("auto"),
        store: JobStore = Depends(get_job_store),
        batches: BatchStore = Depends(get_batch_store),
    ) -> BatchResponse:
        if not query.strip():
            raise HTTPException(status_code=400, detail={"message": "Query is required"})
        if fps <= 0:
            raise HTTPException(status_code=400, detail={"message": "fps must be greater than zero"})
        if topK <= 0:
            raise HTTPException(status_code=400, detail={"message": "topK must be greater than zero"})
        if not files:
            raise HTTPException(status_code=400, detail={"message": "Select at least one file for batch analysis"})

        settings = AnalysisSettings(
            fps=fps,
            top_k=topK,
            enable_vlm=enableVlm,
            device=device,
        )

        try:
            if len(files) == 1 and (files[0].filename or "").lower().endswith(".zip"):
                archive = files[0]
                content = await _read_upload_content(archive)
                if not content:
                    raise HTTPException(status_code=400, detail={"message": "Uploaded archive is empty"})
                batch = batches.create_from_zip(
                    filename=archive.filename or "upload.zip",
                    content=content,
                    query=query.strip(),
                    settings=settings,
                    job_store=store,
                )
            else:
                if any((file.filename or "").lower().endswith(".zip") for file in files):
                    raise HTTPException(
                        status_code=400,
                        detail={"message": "Upload one ZIP archive at a time, or upload video files directly."},
                    )
                materialized: list[tuple[str, bytes]] = []
                for file in files:
                    content = await _read_upload_content(file)
                    if not content:
                        materialized.append((file.filename or "upload.bin", b""))
                    else:
                        materialized.append((file.filename or "upload.bin", content))
                batch = batches.create_from_files(
                    files=materialized,
                    source_filename=f"{len(materialized)} selected files",
                    query=query.strip(),
                    settings=settings,
                    job_store=store,
                )
        except BatchValidationError as exc:
            raise _batch_http_error(exc) from exc

        for job_id in batch.job_ids:
            background_tasks.add_task(execute_analysis_job, store, job_id)
        return BatchResponse(**batch.payload())

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

    @app.get("/api/batches/{batch_id}", response_model=BatchResponse)
    def batch_status(
        batch_id: str,
        store: JobStore = Depends(get_job_store),
        batches: BatchStore = Depends(get_batch_store),
    ) -> BatchResponse:
        record = batches.get(batch_id, store)
        if record is None:
            raise HTTPException(status_code=404, detail={"message": "Batch not found"})
        return BatchResponse(**record.payload())

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

    @app.delete("/api/batches/{batch_id}")
    def delete_batch(
        batch_id: str,
        store: JobStore = Depends(get_job_store),
        batches: BatchStore = Depends(get_batch_store),
    ):
        if not batches.delete(batch_id, store):
            raise HTTPException(status_code=404, detail={"message": "Batch not found"})
        return {"batchId": batch_id, "status": "deleted"}

    _configure_frontend_static(app)

    return app


app = create_app()
