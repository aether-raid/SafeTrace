"""Crash-isolated lightweight VLM worker entrypoint."""
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


def _bounded_int(value: Any, *, default: int, minimum: int, maximum: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        parsed = default
    return max(minimum, min(maximum, parsed))


def _bounded_float(value: Any, *, default: float, minimum: float, maximum: float) -> float:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        parsed = default
    return max(minimum, min(maximum, parsed))


def _preview(text: str | None, *, limit: int = 240) -> str | None:
    if not text:
        return None
    compact = " ".join(str(text).split())
    return compact[:limit]


def _configure_worker_env(
    app_root: Path | None,
    model_dir: Path | None,
    *,
    max_tokens: int,
    generation_timeout_seconds: float,
) -> None:
    os.environ.setdefault("KMP_DUPLICATE_LIB_OK", "TRUE")
    os.environ.setdefault("OMP_NUM_THREADS", "1")
    os.environ.setdefault("SAFETRACE_DEVICE", "cpu")
    os.environ["SAFETRACE_ANALYSIS_SAFE_MODE"] = "false"
    os.environ["SAFETRACE_ENABLE_VLM"] = "true"
    os.environ["SAFETRACE_VLM_ENABLED"] = "true"
    os.environ["SAFETRACE_VLM_PROVIDER"] = "auto"
    os.environ["SAFETRACE_VLM_PROFILE"] = "lightweight_256m"
    os.environ["SAFETRACE_VLM_MAX_TOKENS"] = str(max_tokens)
    os.environ["SAFETRACE_VLM_TIMEOUT_SECONDS"] = f"{generation_timeout_seconds:.1f}"
    if app_root is not None:
        os.environ.setdefault("SAFETRACE_APP_ROOT", str(app_root))
        os.environ.setdefault("SAFETRACE_PROJECT_ROOT", str(app_root))
        os.environ.setdefault("SAFETRACE_DATA_DIR", str(app_root / "data"))
        os.environ.setdefault("SAFETRACE_CHECKPOINTS_DIR", str(app_root / "checkpoints"))
        os.environ.setdefault("SAFETRACE_VLM_DIR", str(app_root / "models" / "vlm"))
        os.environ.setdefault("SAFETRACE_VLM_LIGHTWEIGHT_MODEL_PATH", str(app_root / "models" / "vlm" / "lightweight-256m"))
    if model_dir is not None:
        os.environ["SAFETRACE_VLM_MODEL_PATH"] = str(model_dir)
        os.environ["SAFETRACE_VLM_LIGHTWEIGHT_MODEL_PATH"] = str(model_dir)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run one lightweight VLM explanation request outside the API process")
    parser.add_argument("--input-json", "--input", dest="input_json", type=Path, required=True)
    parser.add_argument("--output-json", "--output", dest="output_json", type=Path, required=True)
    parser.add_argument("--app-root", type=Path, default=None)
    return parser.parse_args(argv)


def run_worker(input_json: Path, output_json: Path, *, app_root: Path | None = None) -> int:
    try:
        request = json.loads(input_json.read_text(encoding="utf-8-sig"))
        model_dir = Path(str(request.get("modelDir") or ""))
        if not model_dir.is_absolute() and app_root is not None:
            model_dir = (app_root / model_dir).resolve()
        worker_timeout_seconds = _bounded_float(
            request.get("timeoutSeconds"),
            default=120.0,
            minimum=15.0,
            maximum=300.0,
        )
        max_tokens = _bounded_int(
            request.get("maxTokens"),
            default=64,
            minimum=24,
            maximum=96,
        )
        generation_timeout_seconds = _bounded_float(
            request.get("generationTimeoutSeconds"),
            default=max(20.0, worker_timeout_seconds - 10.0),
            minimum=10.0,
            maximum=max(10.0, worker_timeout_seconds - 2.0),
        )
        _configure_worker_env(
            app_root.resolve() if app_root is not None else None,
            model_dir,
            max_tokens=max_tokens,
            generation_timeout_seconds=generation_timeout_seconds,
        )

        image_path = Path(str(request["imagePath"]))
        device = str(request.get("device") or "cpu")

        from .schemas import Violation
        from .utils import imread_rgb
        from .vlm_reasoner import VlmReasoner, is_useful_vlm_output

        violations: List[Violation] = []
        for item in list(request.get("violations") or []):
            violations.append(
                Violation(
                    name=str(item.get("name") or "violation"),
                    description=str(item.get("description") or ""),
                    severity=str(item.get("severity") or "medium"),
                    confidence=float(item.get("confidence") or 0.0),
                )
            )

        reasoner = VlmReasoner(model_dir=model_dir, device=device, enabled=True)
        image = imread_rgb(image_path)
        explanation = reasoner.explain_violation(image, violations)
        source = str(getattr(reasoner, "last_explanation_source", "rule_based") or "rule_based")
        if source == "vlm_local":
            source = "vlm_lightweight"

        if source != "vlm_lightweight" or not is_useful_vlm_output(explanation):
            fallback_reason = str(
                getattr(reasoner, "last_fallback_reason", None)
                or source
                or "worker_fallback"
            )
            _write_json(
                output_json,
                {
                    "ok": False,
                    "errorType": "VlmFallback",
                    "fallbackReason": fallback_reason,
                    "explanationSource": "rule_based",
                    "modelProfile": "lightweight_256m",
                    "qualityIssue": getattr(reasoner, "last_quality_issue", None),
                    "rawTextPreview": _preview(getattr(reasoner, "last_raw_vlm_text", None)),
                    "cleanTextPreview": _preview(getattr(reasoner, "last_clean_vlm_text", None)),
                    "generationTimeoutSeconds": generation_timeout_seconds,
                    "maxTokens": max_tokens,
                },
            )
            return 3

        _write_json(
            output_json,
            {
                "ok": True,
                "explanation": explanation,
                "explanationSource": "vlm_lightweight",
                "modelProfile": "lightweight_256m",
                "quality": "accepted",
                "generationTimeoutSeconds": generation_timeout_seconds,
                "maxTokens": max_tokens,
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
                "fallbackReason": type(exc).__name__,
                "traceback": traceback.format_exc(limit=6),
                "explanationSource": "rule_based",
                "modelProfile": "lightweight_256m",
            },
        )
        return 1


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    return run_worker(args.input_json, args.output_json, app_root=args.app_root)


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
