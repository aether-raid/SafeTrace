"""Frame sampling and embedding-window helpers."""
from __future__ import annotations

from typing import Sequence

import numpy as np


def sampling_step(source_fps: float, target_fps: float) -> int:
    """Return the frame interval needed to sample at ``target_fps``."""
    source = source_fps if source_fps and source_fps > 0 else 30.0
    target = max(float(target_fps or 0.0), 1e-6)
    return max(int(round(source / target)), 1)


def build_frame_windows(
    frame_records: Sequence[dict],
    window_size: int = 1,
    stride: int = 1,
) -> list[dict]:
    """Create overlapping frame windows with audit metadata."""
    if not frame_records:
        return []

    size = max(int(window_size or 1), 1)
    step = max(int(stride or 1), 1)
    windows: list[dict] = []

    start = 0
    while start < len(frame_records):
        end = min(start + size, len(frame_records))
        members = list(frame_records[start:end])
        if not members:
            break

        rep_idx = len(members) // 2
        rep = members[rep_idx]
        frame_indices = [
            int(m.get("frame_index", m.get("sample_index", start + offset)))
            for offset, m in enumerate(members)
        ]
        timestamps = [float(m.get("timestamp", 0.0)) for m in members]
        window_id = f"{rep.get('video_id', rep.get('source_id', 'media'))}_w{len(windows):06d}"

        metadata = {
            "frame_id": str(rep.get("frame_id", window_id)),
            "frame_path": str(rep["frame_path"]),
            "index": len(windows),
            "window_id": window_id,
            "window_start_index": start,
            "window_end_index": end - 1,
            "window_frame_indices": frame_indices,
            "window_timestamps": timestamps,
            "timestamp": float(timestamps[rep_idx]) if timestamps else 0.0,
            "start_time": float(timestamps[0]) if timestamps else 0.0,
            "end_time": float(timestamps[-1]) if timestamps else 0.0,
            "representative_frame_path": str(rep["frame_path"]),
            "representative_frame_id": str(rep.get("frame_id", window_id)),
            "source_frame_paths": [str(m["frame_path"]) for m in members],
        }
        for key in (
            "batch_id",
            "vehicle_id",
            "video_id",
            "source_path",
            "original_relative_path",
            "filename",
        ):
            if key in rep:
                metadata[key] = rep[key]
        windows.append(metadata)

        if end >= len(frame_records):
            break
        start += step

    return windows


def pool_window_embeddings(
    frame_embeddings: np.ndarray,
    windows: Sequence[dict],
) -> np.ndarray:
    """Mean-pool frame embeddings into window embeddings."""
    if not windows:
        dim = frame_embeddings.shape[1] if frame_embeddings.ndim == 2 else 0
        return np.zeros((0, dim), dtype=np.float32)

    pooled = []
    for window in windows:
        start = int(window["window_start_index"])
        end = int(window["window_end_index"]) + 1
        pooled.append(frame_embeddings[start:end].mean(axis=0))
    arr = np.stack(pooled).astype(np.float32)
    norm = np.linalg.norm(arr, axis=-1, keepdims=True)
    return arr / np.clip(norm, 1e-12, None)
