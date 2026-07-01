"""Crash-isolated MobileSAM worker entrypoint."""
from __future__ import annotations

import argparse
import json
import os
import sys
import traceback
from pathlib import Path
from typing import Any, Dict, List


def _write_json(path: Path, payload: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")


def _configure_worker_env(app_root: Path | None) -> None:
    os.environ.setdefault("KMP_DUPLICATE_LIB_OK", "TRUE")
    os.environ.setdefault("OMP_NUM_THREADS", "1")
    os.environ.setdefault("SAFETRACE_DEVICE", "cpu")
    if app_root is not None:
        os.environ.setdefault("SAFETRACE_APP_ROOT", str(app_root))
        os.environ.setdefault("SAFETRACE_PROJECT_ROOT", str(app_root))
        os.environ.setdefault("SAFETRACE_DATA_DIR", str(app_root / "data"))
        os.environ.setdefault("SAFETRACE_CHECKPOINTS_DIR", str(app_root / "checkpoints"))
        os.environ.setdefault("SAFETRACE_MOBILESAM_CHECKPOINT", str(app_root / "checkpoints" / "mobile_sam.pt"))


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run one MobileSAM refinement request outside the API process")
    parser.add_argument("--input-json", "--input", dest="input_json", type=Path, required=True)
    parser.add_argument("--output-json", "--output", dest="output_json", type=Path, required=True)
    parser.add_argument("--app-root", type=Path, default=None)
    return parser.parse_args(argv)


def run_worker(input_json: Path, output_json: Path, *, app_root: Path | None = None) -> int:
    _configure_worker_env(app_root.resolve() if app_root is not None else None)
    try:
        request = json.loads(input_json.read_text(encoding="utf-8"))
        image_path = Path(str(request["imagePath"]))
        checkpoint = Path(str(request.get("checkpoint") or os.environ.get("SAFETRACE_MOBILESAM_CHECKPOINT", "")))
        device = str(request.get("device") or "cpu")

        from .mask_encoding import encode_bool_mask
        from .mobile_sam_segmenter import MobileSamSegmenter
        from .schemas import Detection

        detections: List[Detection] = []
        for item in list(request.get("detections") or []):
            bbox = [float(value) for value in list(item.get("bbox") or [0, 0, 0, 0])[:4]]
            while len(bbox) < 4:
                bbox.append(0.0)
            detections.append(
                Detection(
                    label=str(item.get("label") or item.get("raw_label") or "object"),
                    raw_label=str(item.get("raw_label") or item.get("label") or "object"),
                    confidence=float(item.get("confidence") or 0.0),
                    bbox=bbox,
                )
            )

        segmenter = MobileSamSegmenter(checkpoint=checkpoint, device=device)
        if not segmenter.available:
            _write_json(
                output_json,
                {
                    "ok": False,
                    "errorType": "MobileSamUnavailable",
                    "errorMessage": "MobileSAM runtime or checkpoint is unavailable in the worker process.",
                    "detections": [],
                },
            )
            return 2

        refined = segmenter.refine(image_path, detections)
        payload_detections = []
        for index, detection in enumerate(refined):
            payload_detections.append(
                {
                    "index": index,
                    "label": detection.label,
                    "hasRefinedMask": detection.refined_mask is not None,
                    "refinedMask": encode_bool_mask(detection.refined_mask),
                }
            )
        _write_json(
            output_json,
            {
                "ok": True,
                "detections": payload_detections,
                "refinedCount": sum(1 for item in payload_detections if item["hasRefinedMask"]),
            },
        )
        return 0
    except Exception as exc:  # pragma: no cover - defensive subprocess boundary
        _write_json(
            output_json,
            {
                "ok": False,
                "errorType": type(exc).__name__,
                "errorMessage": str(exc),
                "traceback": traceback.format_exc(limit=6),
                "detections": [],
            },
        )
        return 1


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    return run_worker(args.input_json, args.output_json, app_root=args.app_root)


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
