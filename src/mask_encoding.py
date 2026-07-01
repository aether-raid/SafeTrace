"""JSON-safe helpers for moving binary masks between worker processes."""
from __future__ import annotations

from typing import Any, Dict, List, Optional

import numpy as np


def encode_bool_mask(mask: Optional[np.ndarray]) -> Optional[Dict[str, Any]]:
    """Encode a 2D bool mask as simple run-length JSON."""
    if mask is None:
        return None
    arr = np.asarray(mask, dtype=bool)
    if arr.ndim != 2:
        return None
    flat = arr.ravel(order="C")
    if flat.size == 0:
        return {"shape": [int(arr.shape[0]), int(arr.shape[1])], "startsWith": 0, "counts": []}

    counts: List[int] = []
    current = bool(flat[0])
    run = 1
    for value in flat[1:]:
        next_value = bool(value)
        if next_value == current:
            run += 1
        else:
            counts.append(run)
            current = next_value
            run = 1
    counts.append(run)
    return {
        "shape": [int(arr.shape[0]), int(arr.shape[1])],
        "startsWith": 1 if bool(flat[0]) else 0,
        "counts": counts,
    }


def decode_bool_mask(payload: Any) -> Optional[np.ndarray]:
    """Decode a mask produced by :func:`encode_bool_mask`."""
    if not isinstance(payload, dict):
        return None
    shape = payload.get("shape")
    counts = payload.get("counts")
    if (
        not isinstance(shape, list)
        or len(shape) != 2
        or not all(isinstance(value, int) for value in shape)
        or not isinstance(counts, list)
    ):
        return None
    height, width = int(shape[0]), int(shape[1])
    if height <= 0 or width <= 0:
        return None
    values: List[bool] = []
    current = bool(int(payload.get("startsWith") or 0))
    for count in counts:
        try:
            run = int(count)
        except (TypeError, ValueError):
            return None
        if run < 0:
            return None
        values.extend([current] * run)
        current = not current
    expected = height * width
    if len(values) != expected:
        return None
    return np.asarray(values, dtype=bool).reshape((height, width), order="C")
