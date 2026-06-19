"""Pydantic schemas for the local SafeTrace API."""
from __future__ import annotations

from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field


DeviceMode = Literal["auto", "cpu", "cuda"]
JobStatus = Literal["queued", "running", "completed", "failed", "cancelled"]


class HealthResponse(BaseModel):
    status: Literal["ok"]
    api: Literal["safetrace-local"]
    version: str
    offline: bool


class ModelStatus(BaseModel):
    status: Literal["ready", "missing", "unavailable"]
    path: Optional[str] = None
    message: Optional[str] = None


class SystemStatusResponse(BaseModel):
    device: str
    gpuAvailable: bool
    models: Dict[str, ModelStatus]


class AnalyzeResponse(BaseModel):
    jobId: str
    status: JobStatus


class JobStatusResponse(BaseModel):
    jobId: str
    status: JobStatus
    progress: float = Field(ge=0.0, le=1.0)
    currentStep: str
    error: Optional[str] = None


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


class FrameResult(BaseModel):
    id: str
    frameNumber: int
    timestamp: str
    queryRelevance: float
    status: Literal["violations_detected", "no_violations"]
    imageUrl: Optional[str] = None
    imageMessage: Optional[str] = None
    violations: List[FrameViolation]
    technicalEvidence: Dict[str, Any]


class AnalysisResultResponse(BaseModel):
    jobId: str
    status: Literal["completed"]
    media: MediaSummary
    query: str
    summary: AnalysisSummary
    violations: List[GroupedViolation]
    frames: List[FrameResult]
    technicalDetails: Optional[Dict[str, Any]] = None

