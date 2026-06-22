"""Compare SafeTrace embedding pooling strategies without model inference.

By default this script uses a small deterministic synthetic embedding matrix.
Pass ``--embeddings-npy`` to compare mean and max pooling on an existing
embedding matrix. The script does not read videos, run detectors, or load model
checkpoints.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Any, Dict, List

import numpy as np

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.preprocessing import build_frame_windows, pool_embeddings


def load_embeddings(path: Path | None) -> np.ndarray:
    if path is None:
        return np.array(
            [
                [1.0, 0.0, 0.2],
                [0.0, 1.0, 0.3],
                [0.5, 0.5, 0.7],
                [0.2, 0.1, 1.0],
            ],
            dtype=np.float32,
        )
    return np.load(path).astype(np.float32)


def compare_strategies(
    embeddings: np.ndarray,
    *,
    window_size: int,
    stride: int,
) -> List[Dict[str, Any]]:
    frame_paths = [Path(f"frame_{index:06d}.jpg") for index in range(len(embeddings))]
    windows = build_frame_windows(frame_paths, window_size=window_size, stride=stride)
    rows: List[Dict[str, Any]] = []
    for strategy in ("mean", "max"):
        started = time.perf_counter()
        pooled = pool_embeddings(embeddings, windows, strategy=strategy)
        duration = time.perf_counter() - started
        rows.append(
            {
                "poolingStrategy": strategy,
                "sampledFrameCount": int(len(embeddings)),
                "processingWindowCount": len(windows),
                "pooledVectorCount": int(len(pooled)),
                "meanVectorNorm": float(np.linalg.norm(pooled, axis=1).mean()) if len(pooled) else 0.0,
                "meanActivation": float(np.mean(pooled)) if len(pooled) else 0.0,
                "processingDurationSeconds": duration,
            }
        )
    return rows


def main() -> int:
    parser = argparse.ArgumentParser(description="Compare mean and max embedding pooling.")
    parser.add_argument("--embeddings-npy", type=Path, default=None, help="Optional existing embeddings .npy file.")
    parser.add_argument("--window-size", type=int, default=2, help="Number of frames per pooling window.")
    parser.add_argument("--stride", type=int, default=1, help="Window stride.")
    args = parser.parse_args()

    embeddings = load_embeddings(args.embeddings_npy)
    rows = compare_strategies(embeddings, window_size=args.window_size, stride=args.stride)
    print(json.dumps({"results": rows}, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
