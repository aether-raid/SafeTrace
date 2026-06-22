"""Preprocessing metadata and embedding-window helpers.

These helpers are intentionally model-agnostic. They describe how sampled
frames are grouped for indexing and compare simple pooling strategies without
changing detector thresholds, detector classes, model weights, or rule logic.
"""
from __future__ import annotations

import math
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Dict, Sequence

import numpy as np


SUPPORTED_POOLING_STRATEGIES = {"mean", "max"}


@dataclass(frozen=True)
class FrameWindow:
    window_id: str
    frame_indices: list[int]
    frame_paths: list[str]
    representative_frame_path: str
    start_index: int
    end_index: int

    def to_metadata(self) -> Dict[str, Any]:
        payload = asdict(self)
        payload["supportingFrameCount"] = len(self.frame_indices)
        return payload


def normalize_pooling_strategy(strategy: str | None) -> str:
    normalized = (strategy or "mean").strip().lower()
    if normalized not in SUPPORTED_POOLING_STRATEGIES:
        raise ValueError(
            f"Unsupported pooling strategy '{strategy}'. "
            f"Supported strategies: {', '.join(sorted(SUPPORTED_POOLING_STRATEGIES))}."
        )
    return normalized


def build_frame_windows(
    frame_paths: Sequence[str | Path],
    *,
    window_size: int = 1,
    stride: int | None = None,
) -> list[FrameWindow]:
    paths = [Path(path) for path in frame_paths]
    if not paths:
        return []

    size = max(int(window_size or 1), 1)
    step = max(int(stride or size), 1)
    windows: list[FrameWindow] = []

    start = 0
    while start < len(paths):
        end = min(start + size, len(paths))
        indices = list(range(start, end))
        selected = paths[start:end]
        representative = selected[0]
        windows.append(
            FrameWindow(
                window_id=f"window_{len(windows):06d}",
                frame_indices=indices,
                frame_paths=[str(path) for path in selected],
                representative_frame_path=str(representative),
                start_index=start,
                end_index=end - 1,
            )
        )
        if end == len(paths):
            break
        start += step

    return windows


def _l2_normalize(x: np.ndarray) -> np.ndarray:
    norm = np.linalg.norm(x, axis=-1, keepdims=True)
    return x / np.clip(norm, 1e-12, None)


def pool_embeddings(
    embeddings: np.ndarray,
    windows: Sequence[FrameWindow],
    *,
    strategy: str = "mean",
) -> np.ndarray:
    pooling = normalize_pooling_strategy(strategy)
    if embeddings.ndim != 2:
        raise ValueError("Embeddings must be a 2-D array.")
    if not windows:
        return np.zeros((0, embeddings.shape[1]), dtype=np.float32)

    pooled: list[np.ndarray] = []
    for window in windows:
        if not window.frame_indices:
            continue
        if max(window.frame_indices) >= len(embeddings):
            raise IndexError("Frame window references an embedding outside the embedding array.")
        values = embeddings[window.frame_indices]
        if pooling == "mean":
            pooled.append(values.mean(axis=0))
        elif pooling == "max":
            pooled.append(values.max(axis=0))

    if not pooled:
        return np.zeros((0, embeddings.shape[1]), dtype=np.float32)
    return _l2_normalize(np.vstack(pooled).astype(np.float32)).astype(np.float32)


def build_processing_metadata(
    *,
    sampled_frame_count: int,
    sampling_strategy: str,
    fps: float | None,
    max_frames: int | None,
    embedding_batch_size: int,
    embedding_window_size: int,
    embedding_window_stride: int,
    embedding_pooling_strategy: str,
    processing_window_count: int | None = None,
    source_video_duration_seconds: float | None = None,
    source_video_frame_count: int | None = None,
) -> Dict[str, Any]:
    window_count = processing_window_count if processing_window_count is not None else sampled_frame_count
    batch_count = math.ceil(max(sampled_frame_count, 0) / max(int(embedding_batch_size or 1), 1))
    return {
        "samplingStrategy": sampling_strategy,
        "samplingFps": fps,
        "maxSampledFrames": max_frames,
        "sampledFrameCount": sampled_frame_count,
        "processingWindowCount": window_count,
        "embeddingBatchCount": batch_count,
        "embeddingBatchSize": embedding_batch_size,
        "embeddingWindowSize": max(int(embedding_window_size or 1), 1),
        "embeddingWindowStride": max(int(embedding_window_stride or 1), 1),
        "embeddingPoolingStrategy": normalize_pooling_strategy(embedding_pooling_strategy),
        "sourceVideoDurationSeconds": source_video_duration_seconds,
        "sourceVideoFrameCount": source_video_frame_count,
    }
