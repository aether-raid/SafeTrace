"""Detector configuration helpers that do not import ML/image libraries."""
from __future__ import annotations

import logging
from pathlib import Path

from .config import SETTINGS

logger = logging.getLogger("safetrace.detector")


def resolve_detector_checkpoint(
    custom_checkpoint: str | Path | None = None,
    default_checkpoint: str | Path | None = None,
    fallback_checkpoint: str | Path | None = None,
) -> Path:
    """Choose a detector checkpoint with a safe custom->default->fallback order."""
    custom = Path(custom_checkpoint) if custom_checkpoint else None
    default = Path(default_checkpoint or SETTINGS.yolo_checkpoint)
    fallback = Path(fallback_checkpoint or SETTINGS.yolo_fallback_checkpoint)

    if custom is not None:
        if custom.exists():
            return custom
        logger.warning(
            "Custom detector weights %s missing; falling back to default detector.",
            custom,
        )
    if default.exists():
        return default
    if fallback.exists():
        logger.warning("YOLO ckpt %s missing; falling back to %s", default, fallback)
        return fallback
    raise FileNotFoundError(
        f"No YOLO checkpoint found at {default} or {fallback}. "
        "Place a *-seg.pt checkpoint in the checkpoints/ folder, or set "
        "SAFETRACE_DETECTOR_WEIGHTS to a valid custom checkpoint."
    )
