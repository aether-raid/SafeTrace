"""FastAPI app for the local SafeTrace backend."""
from __future__ import annotations

import os
import sys
from importlib import util as importlib_util
from pathlib import Path
from typing import Optional

os.environ.setdefault("KMP_DUPLICATE_LIB_OK", "TRUE")
os.environ.setdefault("OMP_NUM_THREADS", "1")

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
from src.vlm_reasoner import path_has_vlm_model_files, vlm_status_payload

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
    VlmSettingsRequest,
    VlmSettingsResponse,
)


LOCAL_FRONTEND_ORIGINS = (
    "http://127.0.0.1:5173",
    "http://localhost:5173",
)
PNA_REQUEST_HEADER = "access-control-request-private-network"
PNA_RESPONSE_HEADER = "Access-Control-Allow-Private-Network"
VLM_PROFILE_RULE_BASED = "rule_based"
VLM_PROFILE_LIGHTWEIGHT = "lightweight_256m"
VLM_PROFILE_ENHANCED = "enhanced_2b"
VLM_PROFILE_IDS = {VLM_PROFILE_RULE_BASED, VLM_PROFILE_LIGHTWEIGHT, VLM_PROFILE_ENHANCED}
VLM_PROFILE_LABELS = {
    VLM_PROFILE_RULE_BASED: "Rule-based",
    VLM_PROFILE_LIGHTWEIGHT: "Lightweight VLM (256M)",
    VLM_PROFILE_ENHANCED: "Enhanced VLM (2B)",
}


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


def _is_private_network_preflight(request: Request) -> bool:
    return (
        request.method == "OPTIONS"
        and request.headers.get(PNA_REQUEST_HEADER, "").lower() == "true"
        and _is_cors_origin_allowed(request.headers.get("origin"))
    )


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
        if _is_private_network_preflight(request):
            response.headers[PNA_RESPONSE_HEADER] = "true"
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


def _path_has_model_contents(path: Path) -> bool:
    return path_has_vlm_model_files(path)


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


def _optional_mode(value: str | None) -> str:
    raw = (value or "auto").strip().lower()
    if raw in {"0", "false", "no", "off", "disabled", "none"}:
        return "disabled"
    if raw in {"1", "true", "yes", "on", "enabled"}:
        return "enabled"
    return "auto"


def _vlm_enabled_mode() -> str:
    return _optional_mode(getattr(SETTINGS, "vlm_enabled", "auto"))


def _analysis_safe_mode() -> bool:
    return bool(getattr(SETTINGS, "analysis_safe_mode", False))


def _safe_mode_allow_mobile_sam() -> bool:
    return _analysis_safe_mode() and bool(getattr(SETTINGS, "safe_mode_allow_mobilesam", False))


def _mobile_sam_worker_enabled() -> bool:
    return bool(getattr(SETTINGS, "mobile_sam_worker_enabled", False))


def _lightweight_vlm_worker_enabled() -> bool:
    return bool(getattr(SETTINGS, "lightweight_vlm_worker_enabled", False))


def _safe_mode_lightweight_vlm_worker_allowed(profile: str | None = None, enabled: bool | None = None) -> bool:
    selected = (profile or getattr(SETTINGS, "vlm_profile", VLM_PROFILE_RULE_BASED) or VLM_PROFILE_RULE_BASED).strip().lower()
    active_requested = _vlm_enabled_mode() != "disabled" if enabled is None else bool(enabled)
    return bool(
        _analysis_safe_mode()
        and _lightweight_vlm_worker_enabled()
        and active_requested
        and selected == VLM_PROFILE_LIGHTWEIGHT
        and _vlm_enabled_mode() != "disabled"
    )


def _vlm_suppressed_reason(profile: str | None = None, enabled: bool | None = None) -> str | None:
    if _vlm_enabled_mode() == "disabled":
        return "hard_disabled"
    if _analysis_safe_mode() and not _safe_mode_lightweight_vlm_worker_allowed(profile, enabled):
        return "safe_mode"
    return None


def _vlm_hard_disabled(profile: str | None = None, enabled: bool | None = None) -> bool:
    return _vlm_suppressed_reason(profile, enabled) is not None


def _normalized_vlm_profile(value: str | None) -> str:
    raw = (value or VLM_PROFILE_RULE_BASED).strip().lower()
    return raw if raw in VLM_PROFILE_IDS else VLM_PROFILE_RULE_BASED


def _initial_vlm_enabled(profile: str) -> bool:
    if _vlm_hard_disabled(profile, True):
        return False
    if profile == VLM_PROFILE_RULE_BASED:
        return False
    if bool(getattr(SETTINGS, "enable_vlm", False)):
        return True
    return _vlm_enabled_mode() == "enabled"


def _profile_path(profile: str) -> Path | None:
    if profile == VLM_PROFILE_LIGHTWEIGHT:
        return _resolve_configured_path(Path(SETTINGS.vlm_lightweight_model_path))
    if profile == VLM_PROFILE_ENHANCED:
        return _resolve_configured_path(Path(SETTINGS.vlm_enhanced_model_path))
    return None


def _vlm_profile_status(profile: str, *, runtime_available: bool) -> dict:
    if profile == VLM_PROFILE_RULE_BASED:
        return {
            "id": VLM_PROFILE_RULE_BASED,
            "label": VLM_PROFILE_LABELS[VLM_PROFILE_RULE_BASED],
            "installed": True,
            "available": True,
            "requiresActivation": False,
            "resourceLevel": "lowest",
            "path": None,
            "message": "Rule-based explanations are always available.",
        }

    path = _profile_path(profile)
    installed = bool(path and _path_has_model_contents(path))
    return {
        "id": profile,
        "label": VLM_PROFILE_LABELS[profile],
        "installed": installed,
        "available": installed and runtime_available,
        "requiresActivation": True,
        "resourceLevel": "low" if profile == VLM_PROFILE_LIGHTWEIGHT else "high",
        "path": _display_path(path) if path else None,
        "message": (
            "VLM profile is installed and available."
            if installed and runtime_available
            else "VLM profile is installed, but the transformers runtime is unavailable."
            if installed
            else "VLM profile assets are not installed."
        ),
    }


def _vlm_settings_from_state(app: FastAPI | None = None) -> tuple[str, bool]:
    selected_profile = _normalized_vlm_profile(getattr(SETTINGS, "vlm_profile", VLM_PROFILE_RULE_BASED))
    enabled = _initial_vlm_enabled(selected_profile)
    if app is not None:
        selected_profile = _normalized_vlm_profile(getattr(app.state, "vlm_selected_profile", selected_profile))
        enabled = bool(getattr(app.state, "vlm_enabled", enabled)) and selected_profile != VLM_PROFILE_RULE_BASED
    if _vlm_hard_disabled(selected_profile, enabled):
        return selected_profile, False
    return selected_profile, enabled


def _vlm_profiles_payload(*, selected_profile: str, enabled: bool) -> dict:
    suppressed_reason = _vlm_suppressed_reason(selected_profile, enabled)
    lightweight_worker_allowed = _safe_mode_lightweight_vlm_worker_allowed(selected_profile, enabled)
    if suppressed_reason == "safe_mode":
        mobile_sam_allowed = _safe_mode_allow_mobile_sam()
        profiles = [
            {
                "id": VLM_PROFILE_RULE_BASED,
                "label": VLM_PROFILE_LABELS[VLM_PROFILE_RULE_BASED],
                "installed": True,
                "available": True,
                "requiresActivation": False,
                "resourceLevel": "lowest",
                "path": None,
                "message": "Rule-based explanations are active in safe local mode.",
            },
            {
                "id": VLM_PROFILE_LIGHTWEIGHT,
                "label": VLM_PROFILE_LABELS[VLM_PROFILE_LIGHTWEIGHT],
                "installed": False,
                "available": False,
                "requiresActivation": True,
                "resourceLevel": "low",
                "path": None,
                "message": "Not checked in safe local mode.",
            },
            {
                "id": VLM_PROFILE_ENHANCED,
                "label": VLM_PROFILE_LABELS[VLM_PROFILE_ENHANCED],
                "installed": False,
                "available": False,
                "requiresActivation": True,
                "resourceLevel": "high",
                "path": None,
                "message": "Not checked in safe local mode.",
            },
        ]
        return {
            "selectedProfile": selected_profile,
            "enabled": False,
            "active": False,
            "runtimeAvailable": False,
            "profiles": profiles,
            "message": (
                "Safe local mode active. Rule-based explanations only; VLM is disabled. "
                "Experimental MobileSAM may refine selected evidence frames."
                if mobile_sam_allowed
                else "Safe local mode active. Rule-based explanations only; VLM/MobileSAM are disabled for stability."
            ),
            "requestedVisualExplanationMode": selected_profile,
            "actualExplanationMode": "rule_based_with_mobilesam" if mobile_sam_allowed else VLM_PROFILE_RULE_BASED,
            "vlmAvailability": "disabled",
            "vlmSuppressedReason": "safe_mode",
            "fallbackReason": "Safe local mode suppresses VLM.",
            "lightweightModelPathChecked": None,
            "ruleBasedFallbackActive": True,
            "ruleBasedFallbackAvailable": True,
            "safeModeMobileSamAllowed": mobile_sam_allowed,
            "lightweightVlmWorkerEnabled": False,
            "lightweightVlmWorkerTimeoutSeconds": float(
                getattr(SETTINGS, "lightweight_vlm_worker_timeout_seconds", 60.0) or 60.0
            ),
            "lightweightVlmExplanationSource": "disabled",
        }

    runtime_available = _vlm_runtime_available()
    profiles = [
        _vlm_profile_status(VLM_PROFILE_RULE_BASED, runtime_available=runtime_available),
        _vlm_profile_status(VLM_PROFILE_LIGHTWEIGHT, runtime_available=runtime_available),
        _vlm_profile_status(VLM_PROFILE_ENHANCED, runtime_available=runtime_available),
    ]
    profile_by_id = {profile["id"]: profile for profile in profiles}
    selected = profile_by_id.get(selected_profile, profile_by_id[VLM_PROFILE_RULE_BASED])
    hard_disabled = _vlm_hard_disabled(selected_profile, enabled)
    active = bool(not hard_disabled and selected_profile != VLM_PROFILE_RULE_BASED and enabled and selected["available"])
    lightweight_path = _profile_path(VLM_PROFILE_LIGHTWEIGHT)
    actual_mode = selected_profile if active else VLM_PROFILE_RULE_BASED
    vlm_availability = (
        "disabled"
        if hard_disabled
        else "available"
        if bool(selected.get("available"))
        else "missing_runtime"
        if bool(selected.get("installed")) and not runtime_available
        else "missing_assets"
        if selected_profile != VLM_PROFILE_RULE_BASED
        else "rule_based"
    )
    fallback_reason = None
    if hard_disabled:
        message = "VLM is disabled by configuration. Rule-based explanations remain active."
        fallback_reason = "VLM is disabled by SAFETRACE_VLM_ENABLED."
    elif selected_profile == VLM_PROFILE_RULE_BASED:
        message = "Rule-based explanations remain active."
        fallback_reason = "Rule-based mode is selected."
    elif enabled and not selected["available"]:
        message = f"{selected['label']} is unavailable. Rule-based explanations remain active."
        fallback_reason = selected.get("message") or f"{selected['label']} is unavailable."
    elif active and lightweight_worker_allowed:
        message = (
            "Experimental: Lightweight VLM worker selected for evidence explanations. "
            "Rule-based fallback remains active if the worker fails or times out."
        )
    elif active:
        message = (
            f"{selected['label']} selected for the next analysis. Evidence cards only show VLM "
            "when generation succeeds; otherwise rule-based fallback is used."
        )
    else:
        message = f"{selected['label']} available but inactive." if selected["available"] else (
            f"{selected['label']} not installed. Rule-based explanations remain active."
        )
        fallback_reason = "VLM activation is off." if selected["available"] else selected.get("message")
    return {
        "selectedProfile": selected_profile,
        "enabled": bool(not hard_disabled and enabled and selected_profile != VLM_PROFILE_RULE_BASED),
        "active": active,
        "runtimeAvailable": runtime_available,
        "profiles": profiles,
        "message": message,
        "requestedVisualExplanationMode": selected_profile,
        "actualExplanationMode": actual_mode,
        "vlmAvailability": vlm_availability,
        "vlmSuppressedReason": suppressed_reason,
        "fallbackReason": fallback_reason,
        "lightweightModelPathChecked": _display_path(lightweight_path) if lightweight_path else None,
        "ruleBasedFallbackActive": bool(lightweight_worker_allowed or not active),
        "ruleBasedFallbackAvailable": True,
        "lightweightVlmWorkerEnabled": bool(lightweight_worker_allowed),
        "lightweightVlmWorkerTimeoutSeconds": float(
            getattr(SETTINGS, "lightweight_vlm_worker_timeout_seconds", 60.0) or 60.0
        ),
        "lightweightVlmExplanationSource": "worker" if lightweight_worker_allowed and active else "rule_based",
    }


def _current_vlm_payload(app: FastAPI | None = None) -> dict:
    selected_profile, enabled = _vlm_settings_from_state(app)
    return _vlm_profiles_payload(selected_profile=selected_profile, enabled=enabled)


def _vlm_model_status_for_payload(vlm_payload: dict) -> ModelStatus:
    selected_profile = _normalized_vlm_profile(str(vlm_payload.get("selectedProfile") or VLM_PROFILE_RULE_BASED))
    if _vlm_hard_disabled(selected_profile, bool(vlm_payload.get("enabled"))):
        return ModelStatus(**vlm_status_payload())

    if selected_profile == VLM_PROFILE_RULE_BASED:
        return ModelStatus(**vlm_status_payload())

    profiles = {str(profile.get("id")): profile for profile in list(vlm_payload.get("profiles") or [])}
    selected = profiles.get(selected_profile) or {}
    label = str(selected.get("label") or VLM_PROFILE_LABELS[selected_profile])
    path = _profile_path(selected_profile)
    details = {
        "selectedProfile": selected_profile,
        "enabled": bool(vlm_payload.get("enabled")),
        "active": bool(vlm_payload.get("active")),
        "runtimeAvailable": bool(vlm_payload.get("runtimeAvailable")),
        "provider": "local",
        "selectedProvider": "local" if vlm_payload.get("active") else VLM_PROFILE_RULE_BASED,
        "requestedVisualExplanationMode": vlm_payload.get("requestedVisualExplanationMode"),
        "actualExplanationMode": vlm_payload.get("actualExplanationMode"),
        "vlmAvailability": vlm_payload.get("vlmAvailability"),
        "fallbackReason": vlm_payload.get("fallbackReason"),
        "lightweightModelPathChecked": vlm_payload.get("lightweightModelPathChecked"),
        "ruleBasedFallbackActive": vlm_payload.get("ruleBasedFallbackActive"),
        "ruleBasedFallbackAvailable": vlm_payload.get("ruleBasedFallbackAvailable"),
        "lightweightVlmWorkerEnabled": vlm_payload.get("lightweightVlmWorkerEnabled"),
        "lightweightVlmWorkerTimeoutSeconds": vlm_payload.get("lightweightVlmWorkerTimeoutSeconds"),
        "lightweightVlmExplanationSource": vlm_payload.get("lightweightVlmExplanationSource"),
    }
    if bool(vlm_payload.get("active")):
        return ModelStatus(
            status="available",
            path=_display_path(path) if path else None,
            message=f"{label} is selected and available.",
            details=details,
        )
    if bool(selected.get("installed")) and not bool(selected.get("available")):
        return ModelStatus(
            status="missing_runtime",
            path=_display_path(path) if path else None,
            message=f"{label} assets are installed, but the transformers runtime is unavailable.",
            actionHint="Install the local VLM runtime or use rule-based explanations.",
            details=details,
        )
    return ModelStatus(
        status="unavailable",
        path=_display_path(path) if path else None,
        message=f"{label} is not active. Rule-based explanations remain available.",
        actionHint="Install the selected local VLM assets and activate VLM only when needed.",
        details=details,
    )


def _analysis_settings_from_request(
    app: FastAPI,
    *,
    fps: float,
    top_k: int,
    enable_vlm: bool,
    device: str,
    vlm_profile: Optional[str],
    vlm_enabled: Optional[bool],
) -> AnalysisSettings:
    selected_profile, configured_enabled = _vlm_settings_from_state(app)
    requested_profile = _normalized_vlm_profile(vlm_profile or selected_profile)
    safe_mode = _analysis_safe_mode()
    requested_activation = configured_enabled if vlm_enabled is None else bool(vlm_enabled)
    worker_allowed = _safe_mode_lightweight_vlm_worker_allowed(requested_profile, requested_activation)
    requested_activation = bool(
        (not safe_mode or worker_allowed)
        and not _vlm_hard_disabled(requested_profile, requested_activation)
        and requested_activation
        and requested_profile != VLM_PROFILE_RULE_BASED
    )
    effective_vlm_enabled = bool(
        (not safe_mode or worker_allowed)
        and not _vlm_hard_disabled(requested_profile, requested_activation)
        and enable_vlm
        and requested_activation
    )
    return AnalysisSettings(
        fps=fps,
        top_k=top_k,
        enable_vlm=effective_vlm_enabled,
        device="cpu" if safe_mode else device,
        vlm_profile=requested_profile,
        vlm_enabled=requested_activation,
        safe_mode=safe_mode,
    )


def _mobile_sam_runtime_available() -> bool:
    return importlib_util.find_spec("mobile_sam") is not None


def _vlm_runtime_available() -> bool:
    return importlib_util.find_spec("transformers") is not None


def _mobile_sam_status() -> ModelStatus:
    checkpoint = SETTINGS.mobile_sam_checkpoint
    display = _display_path(checkpoint)
    safe_mode = _analysis_safe_mode()
    safe_mode_mobile_sam_allowed = _safe_mode_allow_mobile_sam()
    mode = (
        _optional_mode(getattr(SETTINGS, "mobile_sam_enabled", "auto"))
        if not safe_mode or safe_mode_mobile_sam_allowed
        else "disabled"
    )
    checkpoint_exists = checkpoint.is_file()
    runtime_available = _mobile_sam_runtime_available()
    details = {
        "enabledMode": mode,
        "checkpointExists": checkpoint_exists,
        "runtimeAvailable": runtime_available,
        "packagedExpectedPath": "checkpoints/mobile_sam.pt",
        "safeMode": safe_mode,
        "safeModeMobileSamAllowed": safe_mode_mobile_sam_allowed,
        "mobileSamEnabled": mode != "disabled",
        "mobileSamWorkerEnabled": bool(mode != "disabled" and _mobile_sam_worker_enabled()),
        "mobileSamWorkerTimeoutSeconds": float(getattr(SETTINGS, "mobile_sam_worker_timeout_seconds", 60.0) or 60.0),
        "mobileSamRefinementSource": (
            "worker"
            if mode != "disabled" and _mobile_sam_worker_enabled()
            else "disabled"
            if mode == "disabled"
            else "fallback"
        ),
        "ruleBasedFallbackActive": True,
    }
    if mode == "disabled":
        return ModelStatus(
            status="disabled",
            path=display,
            message=(
                "Safe local mode active. MobileSAM refinement is disabled for stability."
                if _analysis_safe_mode()
                else "MobileSAM refinement is disabled. Detector-box evidence remains available."
            ),
            actionHint="Set SAFETRACE_MOBILESAM_ENABLED=auto to allow optional refinement.",
            details=details,
        )
    if not checkpoint_exists:
        return ModelStatus(
            status="missing_checkpoint",
            path=display,
            message=(
                "MobileSAM checkpoint is missing. SafeTrace will use detector-box evidence without refined masks."
            ),
            actionHint="Place the optional checkpoint at checkpoints/mobile_sam.pt for refined segmentation masks.",
            details=details,
        )
    if not runtime_available:
        return ModelStatus(
            status="missing_runtime",
            path=display,
            message="MobileSAM checkpoint exists, but the mobile-sam Python runtime is unavailable.",
            actionHint="Install the MobileSAM runtime in the local environment, or keep using detector-box fallback.",
            details=details,
        )
    return ModelStatus(
        status="available",
        path=display,
        message=(
            "MobileSAM worker refinement enabled for selected Safe Mode evidence frames. "
            "Detector-box fallback used if the worker fails."
            if safe_mode_mobile_sam_allowed and _mobile_sam_worker_enabled()
            else "Experimental MobileSAM refinement is available for selected Safe Mode evidence frames. "
            "Detector-box rule-based fallback remains active."
            if safe_mode_mobile_sam_allowed
            else "MobileSAM refinement is available as an optional detector-box mask refinement."
        ),
        details=details,
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
    payload = {
        "status": status.status,
        "path": status.path,
        "message": status.message,
    }
    if status.actionHint:
        payload["actionHint"] = status.actionHint
    if status.details:
        payload["details"] = status.details
    return payload


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
    if status.status in {"ready", "available"}:
        return _runtime_check(
            status.status,
            status.message or f"{label} ready",
            path=status.path,
            action_hint=status.actionHint,
            details=status.details,
        )
    if status.status == "disabled":
        return _runtime_check(
            "disabled",
            status.message or f"{label} disabled",
            path=status.path,
            action_hint=status.actionHint,
            details=status.details,
        )
    if status.status in {"missing_checkpoint", "missing_runtime"}:
        return _runtime_check(
            status.status,
            status.message or f"{label} {status.status.replace('_', ' ')}",
            path=status.path,
            action_hint=status.actionHint,
            details=status.details,
        )
    if status.status == "missing":
        return _runtime_check(
            "missing",
            status.message or f"{label} missing",
            path=status.path,
            action_hint=f"Place the required {label} asset at the configured path.",
        )
    action_hint = None if optional else f"Check the configured {label} path."
    if optional and label == "MobileSAM":
        action_hint = "Install checkpoints/mobile_sam.pt only if refined segmentation masks are needed."
    if optional and label == "VLM":
        action_hint = "Use SAFETRACE_VLM_PROVIDER=auto to prefer the local VLM provider, or explicitly choose ollama."
    return _runtime_check(
        "unavailable",
        status.message or f"{label} unavailable",
        path=status.path,
        action_hint=status.actionHint or action_hint,
        details=status.details,
    )


def _visual_explanations_payload(vlm_status: ModelStatus) -> dict:
    details = dict(vlm_status.details or {})
    enhanced_available = vlm_status.status in {"ready", "available"}
    actual_mode = str(details.get("actualExplanationMode") or "").strip() or (
        "vlm" if enhanced_available else "rule_based"
    )
    source = "vlm" if actual_mode not in {"", VLM_PROFILE_RULE_BASED, "rule_based"} and enhanced_available else "rule_based"
    fallback_reason = details.get("fallbackReason")
    return {
        "status": "available",
        "fallback": "rule_based",
        "explanationSource": source,
        "enhancedVlmAvailable": enhanced_available,
        "message": (
            "Visual explanations are enabled. Evidence cards show VLM only when a local VLM "
            "actually generates a clean explanation; rule-based explanations remain the fallback."
        ),
        "requestedVisualExplanationMode": details.get("requestedVisualExplanationMode"),
        "actualExplanationMode": actual_mode,
        "fallbackReason": fallback_reason,
        "ruleBasedFallbackActive": bool(details.get("ruleBasedFallbackActive", source == "rule_based")),
        "lightweightModelPathChecked": details.get("lightweightModelPathChecked"),
        "lightweightVlmWorkerEnabled": details.get("lightweightVlmWorkerEnabled"),
        "lightweightVlmWorkerTimeoutSeconds": details.get("lightweightVlmWorkerTimeoutSeconds"),
        "lightweightVlmExplanationSource": details.get("lightweightVlmExplanationSource"),
    }


def _visual_explanations_preflight_check(vlm_status: ModelStatus) -> dict:
    payload = _visual_explanations_payload(vlm_status)
    return _runtime_check(
        "available",
        payload["message"],
        details={
            "fallback": payload["fallback"],
            "explanationSource": payload["explanationSource"],
            "enhancedVlmAvailable": payload["enhancedVlmAvailable"],
            "enhancedVlmStatus": vlm_status.status,
            "requestedVisualExplanationMode": payload.get("requestedVisualExplanationMode"),
            "actualExplanationMode": payload.get("actualExplanationMode"),
            "fallbackReason": payload.get("fallbackReason"),
            "ruleBasedFallbackActive": payload.get("ruleBasedFallbackActive"),
            "lightweightModelPathChecked": payload.get("lightweightModelPathChecked"),
            "lightweightVlmWorkerEnabled": payload.get("lightweightVlmWorkerEnabled"),
            "lightweightVlmWorkerTimeoutSeconds": payload.get("lightweightVlmWorkerTimeoutSeconds"),
            "lightweightVlmExplanationSource": payload.get("lightweightVlmExplanationSource"),
        },
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
    return _runtime_check(
        state,
        message,
        action_hint=chat.get("action_hint"),
        details={
            "provider": chat.get("provider"),
            "runtimeDiagnostics": chat.get("runtime_diagnostics"),
            "pythonExecutable": chat.get("python_executable"),
            "expectedVenvPython": chat.get("expected_venv_python"),
            "runningInExpectedVenv": chat.get("running_in_expected_venv"),
            "llamaCppImportStatus": chat.get("llama_cpp_import_status"),
            "llamaCppImportErrorType": chat.get("llama_cpp_import_error_type"),
            "llamaCppImportErrorMessage": chat.get("llama_cpp_import_error_message"),
            "setupCommand": chat.get("setup_command"),
            "restartRequired": chat.get("restart_required"),
        },
    )


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
        return _runtime_check(
            "ready",
            "Assistant runtime installed",
            details={
                "runtimeDiagnostics": chat.get("runtime_diagnostics"),
                "pythonExecutable": chat.get("python_executable"),
                "llamaCppImportStatus": chat.get("llama_cpp_import_status"),
            },
        )
    if runtime_available is False:
        return _runtime_check(
            "missing",
            "Assistant runtime is missing.",
            action_hint=chat.get("action_hint"),
            details={
                "runtimeDiagnostics": chat.get("runtime_diagnostics"),
                "pythonExecutable": chat.get("python_executable"),
                "expectedVenvPython": chat.get("expected_venv_python"),
                "runningInExpectedVenv": chat.get("running_in_expected_venv"),
                "llamaCppImportStatus": chat.get("llama_cpp_import_status"),
                "llamaCppSpecFound": chat.get("llama_cpp_spec_found"),
                "llamaCppImportErrorType": chat.get("llama_cpp_import_error_type"),
                "llamaCppImportErrorMessage": chat.get("llama_cpp_import_error_message"),
                "setupCommand": chat.get("setup_command"),
                "restartRequired": chat.get("restart_required"),
            },
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
        "visualExplanations": _visual_explanations_preflight_check(models["vlm"]),
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
        "analysis": {
            "safeMode": _analysis_safe_mode(),
            "safeModeMobileSamAllowed": _safe_mode_allow_mobile_sam(),
            "mobileSamWorkerEnabled": bool(_safe_mode_allow_mobile_sam() and _mobile_sam_worker_enabled()),
            "mobileSamWorkerTimeoutSeconds": float(getattr(SETTINGS, "mobile_sam_worker_timeout_seconds", 60.0) or 60.0),
            "lightweightVlmWorkerEnabled": bool(_safe_mode_lightweight_vlm_worker_allowed()),
            "lightweightVlmWorkerTimeoutSeconds": float(
                getattr(SETTINGS, "lightweight_vlm_worker_timeout_seconds", 60.0) or 60.0
            ),
            "effectiveDevice": "cpu" if _analysis_safe_mode() else SETTINGS.device,
            "safeModeMessage": (
                "Experimental: MobileSAM worker + Lightweight VLM worker. Rule-based fallback active."
                if (
                    _analysis_safe_mode()
                    and _safe_mode_allow_mobile_sam()
                    and _mobile_sam_worker_enabled()
                    and _safe_mode_lightweight_vlm_worker_allowed()
                )
                else
                "Safe local mode active. Rule-based explanations only; MobileSAM worker refinement may run on selected evidence frames."
                if _safe_mode_allow_mobile_sam() and _mobile_sam_worker_enabled()
                else "Safe local mode active. Rule-based explanations only; experimental MobileSAM refinement may run on selected evidence frames."
                if _safe_mode_allow_mobile_sam()
                else "Safe local mode active. Rule-based explanations only; VLM/MobileSAM disabled for stability."
                if _analysis_safe_mode()
                else "Standard analysis mode active."
            ),
            "analysisJobTimeoutSeconds": SETTINGS.analysis_job_timeout_seconds,
        },
        "models": {key: _model_status_payload(value) for key, value in models.items()},
        "visual_explanations": _visual_explanations_payload(models["vlm"]),
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
    initial_vlm_profile = _normalized_vlm_profile(getattr(SETTINGS, "vlm_profile", VLM_PROFILE_RULE_BASED))
    app.state.vlm_selected_profile = initial_vlm_profile
    app.state.vlm_enabled = _initial_vlm_enabled(initial_vlm_profile)
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
    def system_status(request: Request, store: JobStore = Depends(get_job_store)) -> SystemStatusResponse:
        gpu_available = _gpu_available()
        vlm_profiles = _current_vlm_payload(request.app)
        models = {
            "embeddingModel": _path_status(SETTINGS.siglip_model_dir),
            "detector": _detector_status(),
            "mobileSam": _mobile_sam_status(),
            "vlm": _vlm_model_status_for_payload(vlm_profiles),
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
            "analysisSafeMode": _analysis_safe_mode(),
            "analysisJobTimeoutSeconds": SETTINGS.analysis_job_timeout_seconds,
        }
        chat = chat_status_payload(allow_model_load=False)
        openmp = _openmp_status()
        return SystemStatusResponse(
            app_version=__version__,
            backend_version=__version__,
            build_mode=os.environ.get("SAFETRACE_BUILD_MODE", "development"),
            runtime_layout=os.environ.get("SAFETRACE_RUNTIME_LAYOUT", "source"),
            safeMode=_analysis_safe_mode(),
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
            vlm=vlm_profiles,
        )

    @app.post("/api/system/vlm/settings", response_model=VlmSettingsResponse)
    def update_vlm_settings(request: Request, settings: VlmSettingsRequest) -> VlmSettingsResponse:
        request.app.state.vlm_selected_profile = settings.selectedProfile
        request.app.state.vlm_enabled = (
            bool(settings.enabled)
            and settings.selectedProfile != VLM_PROFILE_RULE_BASED
            and not _vlm_hard_disabled(settings.selectedProfile, bool(settings.enabled))
        )
        return VlmSettingsResponse(**_current_vlm_payload(request.app))

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
        request: Request,
        background_tasks: BackgroundTasks,
        file: UploadFile = File(...),
        query: str = Form(...),
        fps: float = Form(1.0),
        topK: int = Form(5),
        enableVlm: bool = Form(False),
        vlmProfile: Optional[str] = Form(None),
        vlmEnabled: Optional[bool] = Form(None),
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
            settings=_analysis_settings_from_request(
                request.app,
                fps=fps,
                top_k=topK,
                enable_vlm=enableVlm,
                device=device,
                vlm_profile=vlmProfile,
                vlm_enabled=vlmEnabled,
            ),
        )
        background_tasks.add_task(execute_analysis_job, store, record.job_id)
        return AnalyzeResponse(jobId=record.job_id, status="queued")

    @app.post("/api/batches/analyze", response_model=BatchResponse)
    async def analyze_batch(
        request: Request,
        background_tasks: BackgroundTasks,
        files: list[UploadFile] = File(...),
        query: str = Form(...),
        fps: float = Form(1.0),
        topK: int = Form(5),
        enableVlm: bool = Form(False),
        vlmProfile: Optional[str] = Form(None),
        vlmEnabled: Optional[bool] = Form(None),
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

        settings = _analysis_settings_from_request(
            request.app,
            fps=fps,
            top_k=topK,
            enable_vlm=enableVlm,
            device=device,
            vlm_profile=vlmProfile,
            vlm_enabled=vlmEnabled,
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
