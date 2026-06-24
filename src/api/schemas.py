"""Pydantic schemas for the local SafeTrace API."""
from __future__ import annotations

from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field


DeviceMode = Literal["auto", "cpu", "cuda"]
JobStatus = Literal["queued", "running", "completed", "failed", "cancelled"]
BatchStatus = Literal["queued", "running", "completed", "failed", "partial", "cancelled"]
ChatAvailabilityState = Literal["available", "disabled", "missing_model", "missing_runtime", "loading", "unavailable"]


class HealthResponse(BaseModel):
    status: Literal["ok"]
    api: Literal["safetrace-local"]
    version: str
    offline: bool


class ModelStatus(BaseModel):
    status: Literal["ready", "available", "missing", "missing_checkpoint", "missing_runtime", "disabled", "unavailable"]
    path: Optional[str] = None
    message: Optional[str] = None
    actionHint: Optional[str] = None
    details: Optional[Dict[str, Any]] = None


class SystemStatusResponse(BaseModel):
    app_version: Optional[str] = None
    backend_version: Optional[str] = None
    build_mode: Optional[str] = None
    runtime_layout: Optional[str] = None
    device: str
    gpuAvailable: bool
    models: Dict[str, ModelStatus]
    limits: Optional[Dict[str, Any]] = None
    queue: Optional[Dict[str, Any]] = None
    runtime: Optional[Dict[str, Any]] = None
    preflight: Optional[Dict[str, Any]] = None


class ChatStatusResponse(BaseModel):
    enabled: bool
    available: bool
    state: ChatAvailabilityState
    status: ChatAvailabilityState
    enabled_mode: str
    provider: str
    model: Optional[str] = None
    model_path: Optional[str] = None
    model_exists: Optional[bool] = None
    runtime_available: Optional[bool] = None
    speed_profile: Optional[str] = None
    warmup_on_open: Optional[bool] = None
    reason: Optional[str] = None
    action_hint: Optional[str] = None
    message: str


class ChatRequest(BaseModel):
    message: str
    job_id: Optional[str] = None
    batch_id: Optional[str] = None
    include_current_result: bool = True


class ChatResponse(BaseModel):
    answer: str
    sources: List[str]
    safeTraceOnly: bool
    modelProvider: str


class AnalyzeResponse(BaseModel):
    jobId: str
    status: JobStatus


class BatchAcceptedFile(BaseModel):
    originalFilename: str
    filename: str
    sizeBytes: int
    mediaType: Literal["video"]
    jobId: str
    status: JobStatus
    error: Optional[str] = None


class BatchRejectedFile(BaseModel):
    filename: str
    reason: str


class BatchResponse(BaseModel):
    batchId: str
    status: BatchStatus
    sourceFilename: str
    acceptedFiles: List[BatchAcceptedFile]
    rejectedFiles: List[BatchRejectedFile]
    jobIds: List[str]
    statusCounts: Dict[str, int]
    createdAt: str
    updatedAt: str


class JobStatusResponse(BaseModel):
    jobId: str
    status: JobStatus
    progress: float = Field(ge=0.0, le=1.0)
    currentStep: str
    error: Optional[str] = None
    metrics: Optional[Dict[str, Any]] = None


class MediaSummary(BaseModel):
    id: str
    name: str
    type: Literal["video", "image", "unknown"]
    sizeBytes: int
    durationSeconds: Optional[float] = None


class AnalysisSummary(BaseModel):
    framesAnalyzed: int
    framesWithViolations: int
    uniqueViolationTypes: int
    highestSeverity: Optional[str] = None
    summaryText: str
    potentialEventCount: Optional[int] = None
    eventTypes: Optional[List[str]] = None
    overallConfidence: Optional[float] = None
    keyEvents: Optional[List[Dict[str, Any]]] = None


class AffectedFrame(BaseModel):
    frameId: str
    frameNumber: int
    timestamp: str
    confidence: float


class GroupedViolation(BaseModel):
    id: str
    name: str
    severity: str
    description: str
    affectedFrames: List[AffectedFrame]
    confidenceMin: float
    confidenceMax: float


class FrameViolation(BaseModel):
    id: str
    name: str
    severity: str
    confidence: float
    description: str


class EventSupportingFrame(BaseModel):
    frameId: str
    frameNumber: int
    timestamp: str
    confidence: float
    imageUrl: Optional[str] = None


class ViolationEvent(BaseModel):
    id: str
    type: str
    name: str
    severity: str
    description: str
    startTimestamp: str
    endTimestamp: str
    representativeConfidence: float
    confidenceMin: float
    confidenceMax: float
    supportingFrameCount: int
    supportingFrames: List[EventSupportingFrame]


class FrameResult(BaseModel):
    id: str
    frameNumber: int
    timestamp: str
    queryRelevance: float
    status: Literal["violations_detected", "no_violations"]
    imageUrl: Optional[str] = None
    imageMessage: Optional[str] = None
    explanationSource: Optional[Literal["vlm", "vlm_local", "vlm_ollama", "rule_based"]] = None
    violations: List[FrameViolation]
    technicalEvidence: Dict[str, Any]


class AnalysisResultResponse(BaseModel):
    jobId: str
    status: Literal["completed"]
    media: MediaSummary
    query: str
    summary: AnalysisSummary
    violations: List[GroupedViolation]
    events: Optional[List[ViolationEvent]] = None
    frames: List[FrameResult]
    technicalDetails: Optional[Dict[str, Any]] = None
