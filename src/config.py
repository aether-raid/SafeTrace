"""Central configuration for SafeTrace.

All paths, thresholds, and toggles live here. Values can be overridden via
environment variables to keep the system fully offline-configurable.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict


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
    frame_fps: float = field(default_factory=lambda: _env_float("SAFETRACE_FPS", 1.0))
    max_frames: int = field(default_factory=lambda: _env_int("SAFETRACE_MAX_FRAMES", 600))
    top_k: int = field(default_factory=lambda: _env_int("SAFETRACE_TOPK", 5))
    embedding_batch_size: int = field(default_factory=lambda: _env_int("SAFETRACE_EMB_BATCH", 16))
    embedding_window_size: int = field(default_factory=lambda: _env_int("SAFETRACE_EMB_WINDOW_SIZE", 1))
    embedding_window_stride: int = field(default_factory=lambda: _env_int("SAFETRACE_EMB_WINDOW_STRIDE", 1))
    embedding_pooling_strategy: str = field(default_factory=lambda: _env("SAFETRACE_EMB_POOLING", "mean"))
    max_video_duration_seconds: float = field(
        default_factory=lambda: _env_float("SAFETRACE_MAX_VIDEO_SECONDS", 0.0)
    )
    worker_concurrency: int = field(default_factory=lambda: _env_int("SAFETRACE_WORKER_CONCURRENCY", 1))

    # ---- Local API hardening ----
    max_upload_mb: float = field(default_factory=lambda: _env_float("SAFETRACE_MAX_UPLOAD_MB", 512.0))
    bulk_max_files: int = field(default_factory=lambda: _env_int("SAFETRACE_BULK_MAX_FILES", 25))
    bulk_max_uncompressed_mb: float = field(
        default_factory=lambda: _env_float("SAFETRACE_BULK_MAX_UNCOMPRESSED_MB", 2048.0)
    )
    job_retention_hours: float = field(default_factory=lambda: _env_float("SAFETRACE_JOB_RETENTION_HOURS", 24.0))
    stale_running_minutes: float = field(default_factory=lambda: _env_float("SAFETRACE_STALE_RUNNING_MINUTES", 30.0))

    # ---- Detection ----
    yolo_conf_threshold: float = field(default_factory=lambda: _env_float("SAFETRACE_YOLO_CONF", 0.25))
    yolo_iou_threshold: float = field(default_factory=lambda: _env_float("SAFETRACE_YOLO_IOU", 0.45))

    # ---- Rule thresholds ----
    helmet_iou_threshold: float = 0.20      # IoU(head, helmet) below => missing
    hands_wheel_iou_threshold: float = 0.10  # IoU(hand, wheel) below => off-wheel
    phone_hand_iou_threshold: float = 0.30   # IoU(phone, hand) above => phone use
    seatbelt_iou_threshold: float = 0.20     # IoU(seatbelt, torso) below => missing

    def ensure_dirs(self) -> None:
        for p in (self.data_dir, self.frames_dir, self.checkpoints_dir):
            p.mkdir(parents=True, exist_ok=True)

    def apply_offline_env(self) -> None:
        """Force HuggingFace / transformers into offline mode."""
        if self.offline:
            os.environ.setdefault("HF_HUB_OFFLINE", "1")
            os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")


# Class label vocabulary used by the rule engine. Different YOLO checkpoints
# may use different label spellings, so each rule key maps to many possible
# raw class names that we treat as equivalent.
CLASS_ALIASES: Dict[str, set[str]] = {
    "person": {"person"},
    "head": {"head", "face"},
    "helmet": {"helmet", "hard hat", "hardhat", "safety helmet"},
    "hand": {"hand", "hands"},
    "steering_wheel": {"steering wheel", "steering_wheel", "wheel"},
    "phone": {"phone", "cell phone", "cellphone", "mobile phone", "smartphone"},
    "seatbelt": {"seatbelt", "seat belt", "seat_belt", "belt"},
    "torso": {"torso", "upper body", "chest"},
}


def normalize_label(raw: str) -> str | None:
    """Map a raw model label to a canonical SafeTrace label, or None."""
    if not raw:
        return None
    needle = raw.strip().lower()
    for canonical, aliases in CLASS_ALIASES.items():
        if needle in aliases:
            return canonical
    return None


SETTINGS = Settings()
SETTINGS.ensure_dirs()
SETTINGS.apply_offline_env()
