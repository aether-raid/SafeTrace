"""Parent-process client for crash-isolated lightweight VLM explanations."""
from __future__ import annotations

import json
import logging
import os
import subprocess
import sys
import uuid
from pathlib import Path
from typing import Any, Dict, Sequence

import numpy as np

from .config import SETTINGS
from .schemas import Violation
from .utils import imwrite_rgb
from .vlm_reasoner import RULE_BASED_PROVIDER, RuleBasedReasoner, is_useful_vlm_output

logger = logging.getLogger("safetrace.vlm.worker")


def _disabled_mode(value: str | None) -> bool:
    return (value or "").strip().lower() in {"0", "false", "no", "off", "disabled", "none"}


def _worker_dir() -> Path:
    path = SETTINGS.data_dir / "lightweight_vlm_worker"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _lightweight_model_path() -> Path:
    path = Path(getattr(SETTINGS, "vlm_lightweight_model_path", SETTINGS.vlm_model_dir))
    if path.is_absolute():
        return path
    cwd_candidate = (Path.cwd() / path).resolve()
    if cwd_candidate.exists():
        return cwd_candidate
    return (SETTINGS.project_root / path).resolve()


class LightweightVlmWorkerReasoner:
    """Lightweight VLM through a subprocess, never in the API process."""

    provider = "vlm_lightweight_worker"

    def __init__(self, model_dir: str | Path | None = None, device: str | None = None) -> None:
        self.model_dir = Path(model_dir or _lightweight_model_path())
        self.device = "cpu"
        self.timeout_seconds = max(
            1.0,
            float(getattr(SETTINGS, "lightweight_vlm_worker_timeout_seconds", 60.0) or 60.0),
        )
        self.enabled = bool(getattr(SETTINGS, "lightweight_vlm_worker_enabled", False)) and not _disabled_mode(
            getattr(SETTINGS, "vlm_enabled", "auto")
        )
        self._available = bool(self.enabled and self.model_dir.exists())
        self._fallback_reasoner = RuleBasedReasoner()
        self.last_explanation_source = RULE_BASED_PROVIDER
        self.last_diagnostics: Dict[str, Any] = self._diagnostics(
            attempted=False,
            succeeded=False,
            timed_out=False,
            exit_code=None,
            source="disabled" if not self.enabled else RULE_BASED_PROVIDER,
            reason=None if self._available else "model_missing" if self.enabled else "worker_disabled",
        )

    @property
    def available(self) -> bool:
        return self._available

    def _diagnostics(
        self,
        *,
        attempted: bool,
        succeeded: bool,
        timed_out: bool,
        exit_code: int | None,
        source: str,
        reason: str | None,
        extra: Dict[str, Any] | None = None,
    ) -> Dict[str, Any]:
        diagnostics = {
            "lightweightVlmWorkerEnabled": bool(self.enabled),
            "lightweightVlmWorkerTimeoutSeconds": self.timeout_seconds,
            "lightweightVlmWorkerAttempted": bool(attempted),
            "lightweightVlmWorkerSucceeded": bool(succeeded),
            "lightweightVlmWorkerTimedOut": bool(timed_out),
            "lightweightVlmWorkerExitCode": exit_code,
            "lightweightVlmFallbackReason": reason,
            "lightweightVlmExplanationSource": source,
        }
        if extra:
            diagnostics.update(extra)
        return diagnostics

    def _fallback(
        self,
        image: np.ndarray,
        violations: Sequence[Violation],
        *,
        reason: str,
        attempted: bool = True,
        timed_out: bool = False,
        exit_code: int | None = None,
        extra: Dict[str, Any] | None = None,
    ) -> str:
        self.last_explanation_source = RULE_BASED_PROVIDER
        self.last_diagnostics = self._diagnostics(
            attempted=attempted,
            succeeded=False,
            timed_out=timed_out,
            exit_code=exit_code,
            source=RULE_BASED_PROVIDER if attempted else "disabled",
            reason=reason,
            extra=extra,
        )
        return self._fallback_reasoner.explain_violation(image, violations)

    def _materialize_image(self, image) -> Path:
        if isinstance(image, (str, Path)):
            return Path(image)
        if not isinstance(image, np.ndarray):
            raise TypeError("Lightweight VLM worker requires an image path or numpy image array.")
        image_path = _worker_dir() / f"frame_{uuid.uuid4().hex}.jpg"
        imwrite_rgb(image_path, image)
        return image_path

    def _command(self, input_path: Path, output_path: Path) -> list[str]:
        app_root = Path(os.environ.get("SAFETRACE_APP_ROOT") or SETTINGS.project_root).resolve()
        if getattr(sys, "frozen", False):
            return [
                sys.executable,
                "--lightweight-vlm-worker",
                "--input-json",
                str(input_path),
                "--output-json",
                str(output_path),
                "--app-root",
                str(app_root),
            ]
        return [
            sys.executable,
            "-m",
            "src.lightweight_vlm_worker",
            "--input-json",
            str(input_path),
            "--output-json",
            str(output_path),
            "--app-root",
            str(app_root),
        ]

    def _request_payload(self, image_path: Path, violations: Sequence[Violation]) -> Dict[str, Any]:
        return {
            "imagePath": str(image_path),
            "modelDir": str(self.model_dir),
            "device": self.device,
            "profile": "lightweight_256m",
            "maxTokens": max(24, min(int(getattr(SETTINGS, "vlm_max_tokens", 64) or 64), 96)),
            "timeoutSeconds": self.timeout_seconds,
            "generationTimeoutSeconds": max(10.0, min(self.timeout_seconds - 2.0, max(20.0, self.timeout_seconds - 10.0))),
            "violations": [
                {
                    "name": violation.name,
                    "description": violation.description,
                    "severity": violation.severity,
                    "confidence": float(violation.confidence),
                }
                for violation in violations
            ],
        }

    def _consume_result(self, output_path: Path, image: np.ndarray, violations: Sequence[Violation]) -> str:
        try:
            payload = json.loads(output_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            return self._fallback(image, violations, reason=f"invalid_worker_json:{type(exc).__name__}", exit_code=0)

        if not bool(payload.get("ok")):
            reason = str(payload.get("fallbackReason") or payload.get("errorType") or "worker_error")
            return self._fallback(
                image,
                violations,
                reason=reason,
                extra={
                    "lightweightVlmQualityIssue": payload.get("qualityIssue"),
                    "lightweightVlmRawTextPreview": payload.get("rawTextPreview"),
                    "lightweightVlmCleanTextPreview": payload.get("cleanTextPreview"),
                    "lightweightVlmGenerationTimeoutSeconds": payload.get("generationTimeoutSeconds"),
                    "lightweightVlmMaxTokens": payload.get("maxTokens"),
                },
            )

        explanation = str(payload.get("explanation") or "").strip()
        if not explanation or not is_useful_vlm_output(explanation):
            return self._fallback(image, violations, reason="low_quality_worker_output")

        self.last_explanation_source = "vlm_lightweight"
        self.last_diagnostics = self._diagnostics(
            attempted=True,
            succeeded=True,
            timed_out=False,
            exit_code=0,
            source="vlm_lightweight",
            reason=None,
            extra={
                "lightweightVlmGenerationTimeoutSeconds": payload.get("generationTimeoutSeconds"),
                "lightweightVlmMaxTokens": payload.get("maxTokens"),
            },
        )
        self.last_diagnostics["lightweightVlmModelProfile"] = str(payload.get("modelProfile") or "lightweight_256m")
        return explanation

    def explain_violation(self, image: np.ndarray, violations: Sequence[Violation]) -> str:
        if not violations:
            return self._fallback(image, violations, reason="no_violations", attempted=False)
        if not self.enabled:
            return self._fallback(image, violations, reason="worker_disabled", attempted=False)
        if not self.model_dir.exists():
            return self._fallback(image, violations, reason="model_missing", attempted=False)

        try:
            image_path = self._materialize_image(image)
            work_dir = _worker_dir()
            request_path = work_dir / f"request_{uuid.uuid4().hex}.json"
            output_path = work_dir / f"result_{uuid.uuid4().hex}.json"
            request_payload = self._request_payload(image_path, violations)
            request_path.write_text(
                json.dumps(request_payload, indent=2, default=str),
                encoding="utf-8",
            )
            env = os.environ.copy()
            app_root = Path(env.get("SAFETRACE_APP_ROOT") or SETTINGS.project_root).resolve()
            env.setdefault("KMP_DUPLICATE_LIB_OK", "TRUE")
            env.setdefault("OMP_NUM_THREADS", "1")
            env.setdefault("SAFETRACE_DEVICE", "cpu")
            env.setdefault("SAFETRACE_VLM_PROVIDER", "auto")
            env.setdefault("SAFETRACE_VLM_PROFILE", "lightweight_256m")
            env.setdefault("SAFETRACE_VLM_MODEL_PATH", str(self.model_dir))
            env.setdefault("SAFETRACE_VLM_LIGHTWEIGHT_MODEL_PATH", str(self.model_dir))
            env.setdefault("SAFETRACE_VLM_MAX_TOKENS", str(request_payload["maxTokens"]))
            result = subprocess.run(
                self._command(request_path, output_path),
                cwd=str(app_root),
                env=env,
                text=True,
                capture_output=True,
                timeout=self.timeout_seconds,
                check=False,
            )
        except subprocess.TimeoutExpired:
            logger.warning("Lightweight VLM worker timed out after %.1fs; using rule-based fallback.", self.timeout_seconds)
            return self._fallback(image, violations, reason="worker_timeout", timed_out=True)
        except Exception as exc:  # pragma: no cover - defensive
            logger.warning("Lightweight VLM worker launch failed: %s", exc)
            return self._fallback(image, violations, reason=f"worker_launch_failed:{type(exc).__name__}")

        if result.returncode != 0:
            reason = f"worker_exit_{result.returncode}"
            extra: Dict[str, Any] = {}
            if output_path.exists():
                try:
                    payload = json.loads(output_path.read_text(encoding="utf-8"))
                    reason = str(payload.get("fallbackReason") or payload.get("errorType") or reason)
                    extra = {
                        "lightweightVlmQualityIssue": payload.get("qualityIssue"),
                        "lightweightVlmRawTextPreview": payload.get("rawTextPreview"),
                        "lightweightVlmCleanTextPreview": payload.get("cleanTextPreview"),
                        "lightweightVlmGenerationTimeoutSeconds": payload.get("generationTimeoutSeconds"),
                        "lightweightVlmMaxTokens": payload.get("maxTokens"),
                    }
                except (OSError, json.JSONDecodeError):
                    pass
            logger.warning("Lightweight VLM worker exited with %s; using rule-based fallback.", result.returncode)
            return self._fallback(image, violations, reason=reason, exit_code=result.returncode, extra=extra)

        return self._consume_result(output_path, image, violations)
