"""Central configuration for SafeTrace.

All paths, thresholds, and toggles live here. Values can be overridden via
environment variables to keep the system fully offline-configurable.
"""
from __future__ import annotations

import os
import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Optional

logger = logging.getLogger("safetrace.config")


def _env(key: str, default: str) -> str:
    return os.environ.get(key, default)


def _env_float(key: str, default: float) -> float:
    try:
        return float(os.environ.get(key, default))
    except (TypeError, ValueError):
        return default


def _env_int(key: str, default: int) -> int:
    try:
        return int(os.environ.get(key, default))
    except (TypeError, ValueError):
        return default


def _env_bool(key: str, default: bool) -> bool:
    raw = os.environ.get(key)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "y", "on"}


def _env_path_optional(key: str) -> Optional[Path]:
    raw = os.environ.get(key)
    if raw is None or not raw.strip():
        return None
    return Path(raw)


PROJECT_ROOT = Path(__file__).resolve().parent.parent


@dataclass
class Settings:
    # ---- Paths ----
    project_root: Path = PROJECT_ROOT
    data_dir: Path = PROJECT_ROOT / "data"
    frames_dir: Path = PROJECT_ROOT / "data" / "frames"
    embeddings_path: Path = PROJECT_ROOT / "data" / "embeddings.npy"
    metadata_path: Path = PROJECT_ROOT / "data" / "metadata.json"
    index_path: Path = PROJECT_ROOT / "data" / "index.faiss"
    jobs_dir: Path = PROJECT_ROOT / "data" / "jobs"
    checkpoints_dir: Path = PROJECT_ROOT / "checkpoints"

    # ---- Models (local checkpoints / local model dirs) ----
    siglip_model_dir: Path = field(
        default_factory=lambda: Path(
            _env("SAFETRACE_SIGLIP_DIR", str(PROJECT_ROOT / "checkpoints" / "siglip-base-patch16-224"))
        )
    )
    yolo_checkpoint: Path = field(
        default_factory=lambda: Path(
            _env("SAFETRACE_YOLO_CKPT", str(PROJECT_ROOT / "checkpoints" / "yolov9c-seg.pt"))
        )
    )
    yolo_fallback_checkpoint: Path = field(
        default_factory=lambda: Path(
            _env("SAFETRACE_YOLO_FALLBACK_CKPT", str(PROJECT_ROOT / "checkpoints" / "yolov8s-seg.pt"))
        )
    )
    custom_detector_weights: Optional[Path] = field(
        default_factory=lambda: _env_path_optional("SAFETRACE_DETECTOR_WEIGHTS")
    )
    detector_classes_path: Optional[Path] = field(
        default_factory=lambda: _env_path_optional("SAFETRACE_DETECTOR_CLASSES_PATH")
    )
    detector_classes_json: str = field(
        default_factory=lambda: _env("SAFETRACE_DETECTOR_CLASSES", "")
    )
    mobile_sam_checkpoint: Path = field(
        default_factory=lambda: Path(
            _env("SAFETRACE_MSAM_CKPT", str(PROJECT_ROOT / "checkpoints" / "mobile_sam.pt"))
        )
    )
    vlm_model_dir: Path = field(
        default_factory=lambda: Path(
            _env("SAFETRACE_VLM_DIR", str(PROJECT_ROOT / "checkpoints" / "vlm_model"))
        )
    )

    # ---- Runtime ----
    device: str = field(default_factory=lambda: _env("SAFETRACE_DEVICE", "auto"))
    offline: bool = field(default_factory=lambda: _env_bool("SAFETRACE_OFFLINE", True))
    enable_vlm: bool = field(default_factory=lambda: _env_bool("SAFETRACE_ENABLE_VLM", False))

    # ---- Sampling / pipeline ----
    frame_fps: float = field(
        default_factory=lambda: _env_float(
            "SAFETRACE_TARGET_FPS", _env_float("SAFETRACE_FPS", 1.0)
        )
    )
    max_frames: int = field(default_factory=lambda: _env_int("SAFETRACE_MAX_FRAMES", 600))
    top_k: int = field(default_factory=lambda: _env_int("SAFETRACE_TOPK", 5))
    embedding_batch_size: int = field(
        default_factory=lambda: _env_int(
            "SAFETRACE_FRAME_BATCH_SIZE", _env_int("SAFETRACE_EMB_BATCH", 16)
        )
    )
    embed_window_size: int = field(default_factory=lambda: _env_int("SAFETRACE_EMBED_WINDOW_SIZE", 1))
    embed_window_stride: int = field(default_factory=lambda: _env_int("SAFETRACE_EMBED_WINDOW_STRIDE", 1))

    # ---- Detection ----
    yolo_conf_threshold: float = field(
        default_factory=lambda: _env_float(
            "SAFETRACE_DETECTOR_CONF_THRESHOLD", _env_float("SAFETRACE_YOLO_CONF", 0.25)
        )
    )
    yolo_iou_threshold: float = field(
        default_factory=lambda: _env_float(
            "SAFETRACE_DETECTOR_IOU_THRESHOLD", _env_float("SAFETRACE_YOLO_IOU", 0.45)
        )
    )

    # ---- Aggregation ----
    seatbelt_grace_seconds: float = field(
        default_factory=lambda: _env_float("SAFETRACE_SEATBELT_GRACE_SECONDS", 15.0)
    )
    event_merge_gap_seconds: float = field(
        default_factory=lambda: _env_float("SAFETRACE_EVENT_MERGE_GAP_SECONDS", 5.0)
    )
    likely_min_evidence_frames: int = field(
        default_factory=lambda: _env_int("SAFETRACE_LIKELY_MIN_EVIDENCE_FRAMES", 3)
    )

    # ---- Jobs / uploads ----
    max_concurrent_jobs: int = field(default_factory=lambda: _env_int("SAFETRACE_MAX_CONCURRENT_JOBS", 1))
    video_batch_size: int = field(default_factory=lambda: _env_int("SAFETRACE_VIDEO_BATCH_SIZE", 1))
    max_upload_size_mb: int = field(default_factory=lambda: _env_int("SAFETRACE_MAX_UPLOAD_SIZE_MB", 51200))
    job_timeout_seconds: int = field(default_factory=lambda: _env_int("SAFETRACE_JOB_TIMEOUT_SECONDS", 0))

    # ---- Rule thresholds ----
    helmet_iou_threshold: float = 0.20      # IoU(head, helmet) below => missing
    hands_wheel_iou_threshold: float = 0.10  # IoU(hand, wheel) below => off-wheel
    phone_hand_iou_threshold: float = 0.30   # IoU(phone, hand) above => phone use
    seatbelt_iou_threshold: float = 0.20     # IoU(seatbelt, torso) below => missing

    def ensure_dirs(self) -> None:
        for p in (self.data_dir, self.frames_dir, self.jobs_dir, self.checkpoints_dir):
            p.mkdir(parents=True, exist_ok=True)

    def apply_offline_env(self) -> None:
        """Force HuggingFace / transformers into offline mode."""
        if self.offline:
            os.environ.setdefault("HF_HUB_OFFLINE", "1")
            os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")


# Class label vocabulary used by the rule engine. Different YOLO checkpoints
# may use different label spellings, so each rule key maps to many possible
# raw class names that we treat as equivalent.
DEFAULT_CLASS_ALIASES: Dict[str, set[str]] = {
    "person": {"person"},
    "head": {"head", "face"},
    "helmet": {"helmet", "hard hat", "hardhat", "safety helmet"},
    "hand": {"hand", "hands"},
    "steering_wheel": {"steering wheel", "steering_wheel", "wheel"},
    "phone": {"phone", "cell phone", "cellphone", "mobile phone", "smartphone"},
    "seatbelt": {"seatbelt", "seat belt", "seat_belt", "belt"},
    "torso": {"torso", "upper body", "chest"},
}


def _canonical_label(label: str) -> str:
    return label.strip().lower().replace("-", "_").replace(" ", "_")


def _load_detector_class_payload() -> dict:
    payloads = []
    inline = os.environ.get("SAFETRACE_DETECTOR_CLASSES", "").strip()
    if inline:
        try:
            payloads.append(json.loads(inline))
        except json.JSONDecodeError as exc:
            logger.warning("Ignoring invalid SAFETRACE_DETECTOR_CLASSES JSON: %s", exc)

    path_raw = os.environ.get("SAFETRACE_DETECTOR_CLASSES_PATH", "").strip()
    if path_raw:
        path = Path(path_raw)
        if path.exists():
            try:
                payloads.append(json.loads(path.read_text(encoding="utf-8")))
            except (OSError, json.JSONDecodeError) as exc:
                logger.warning("Ignoring detector class mapping %s: %s", path, exc)
        else:
            logger.warning("Detector class mapping path %s does not exist; using defaults.", path)

    merged: dict = {"classes": {}, "aliases": {}}
    for payload in payloads:
        if isinstance(payload, list):
            merged["classes"].update({str(i): str(name) for i, name in enumerate(payload)})
        elif isinstance(payload, dict):
            classes = payload.get("classes") or payload.get("class_map") or payload.get("mapping")
            aliases = payload.get("aliases")
            if classes is None and aliases is None:
                classes = payload
            if isinstance(classes, list):
                merged["classes"].update({str(i): str(name) for i, name in enumerate(classes)})
            elif isinstance(classes, dict):
                merged["classes"].update({str(k): str(v) for k, v in classes.items()})
            if isinstance(aliases, dict):
                for key, values in aliases.items():
                    if isinstance(values, str):
                        values = [values]
                    if isinstance(values, list):
                        merged["aliases"].setdefault(str(key), [])
                        merged["aliases"][str(key)].extend(str(v) for v in values)
    return merged


def _build_class_aliases() -> tuple[Dict[str, set[str]], Dict[str, str]]:
    aliases: Dict[str, set[str]] = {k: set(v) for k, v in DEFAULT_CLASS_ALIASES.items()}
    direct_map: Dict[str, str] = {}
    payload = _load_detector_class_payload()

    for raw, canonical in payload.get("classes", {}).items():
        canonical_key = _canonical_label(canonical)
        aliases.setdefault(canonical_key, set()).add(canonical_key)
        aliases[canonical_key].add(str(canonical).strip().lower())
        direct_map[str(raw).strip().lower()] = canonical_key

    for canonical, values in payload.get("aliases", {}).items():
        canonical_key = _canonical_label(canonical)
        aliases.setdefault(canonical_key, set()).add(canonical_key)
        for value in values:
            aliases[canonical_key].add(str(value).strip().lower())

    return aliases, direct_map


CLASS_ALIASES, DETECTOR_CLASS_MAP = _build_class_aliases()


def normalize_label(raw: str, class_id: int | str | None = None) -> str | None:
    """Map a raw model label to a canonical SafeTrace label, or None."""
    if class_id is not None:
        mapped = DETECTOR_CLASS_MAP.get(str(class_id).strip().lower())
        if mapped:
            return mapped
    if not raw:
        return None
    needle = raw.strip().lower()
    mapped = DETECTOR_CLASS_MAP.get(needle)
    if mapped:
        return mapped
    for canonical, aliases in CLASS_ALIASES.items():
        if needle in aliases:
            return canonical
    return None


SETTINGS = Settings()
SETTINGS.ensure_dirs()
SETTINGS.apply_offline_env()
