"""Optional local Vision-Language Model reasoning.

Provides natural-language explanations for detected violations using a small
local VLM such as ``microsoft/Phi-3-vision-128k-instruct`` or
``openbmb/MiniCPM-V``. If the local snapshot is missing or the load fails,
``explain_violation`` falls back to a deterministic, evidence-based summary
so the pipeline never depends on the VLM being present.
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Sequence

import numpy as np
from PIL import Image

from .config import SETTINGS
from .schemas import Violation
from .utils import resolve_device

logger = logging.getLogger("safetrace.vlm")


def _fallback_explanation(violations: Sequence[Violation]) -> str:
    if not violations:
        return "No safety violations were detected in this frame."
    parts = []
    for v in violations:
        ev = ", ".join(f"{k}={val}" for k, val in v.evidence.items())
        parts.append(f"- {v.name} ({v.severity}): {v.description} [{ev}]")
    return "Detected violations:\n" + "\n".join(parts)


class VlmReasoner:
    def __init__(
        self,
        model_dir: str | Path | None = None,
        device: str | None = None,
        enabled: bool | None = None,
    ) -> None:
        self.device = resolve_device(device or SETTINGS.device)
        self.model_dir = Path(model_dir or SETTINGS.vlm_model_dir)
        self.enabled = SETTINGS.enable_vlm if enabled is None else enabled
        self._model = None
        self._processor = None
        self._loaded = False

        if not self.enabled:
            logger.info("VLM disabled by configuration.")
            return
        if not self.model_dir.exists() or not any(self.model_dir.iterdir()):
            logger.warning("VLM model dir empty/missing at %s; disabling.", self.model_dir)
            self.enabled = False
            return

        try:
            import torch
            from transformers import AutoModelForCausalLM, AutoProcessor

            logger.info("Loading VLM from %s on %s", self.model_dir, self.device)
            self._processor = AutoProcessor.from_pretrained(
                str(self.model_dir), trust_remote_code=True, local_files_only=True
            )
            self._model = AutoModelForCausalLM.from_pretrained(
                str(self.model_dir),
                trust_remote_code=True,
                local_files_only=True,
                torch_dtype=torch.float16 if self.device == "cuda" else torch.float32,
            ).to(self.device).eval()
            self._loaded = True
        except Exception as exc:  # pragma: no cover - optional path
            logger.warning("Failed to load VLM (%s); falling back to text-only.", exc)
            self.enabled = False

    # ------------------------------------------------------------------ #
    def explain_violation(self, image: np.ndarray, violations: Sequence[Violation]) -> str:
        if not self.enabled or not self._loaded:
            return _fallback_explanation(violations)

        try:
            import torch

            pil = image if isinstance(image, Image.Image) else Image.fromarray(image)
            names = ", ".join(v.name for v in violations) or "no obvious violations"
            prompt = (
                "You are a workplace safety auditor. Briefly describe what you see "
                f"in this image and explain whether the following potential safety "
                f"violations are clearly visible: {names}. "
                "Respond in 2-3 short sentences."
            )
            inputs = self._processor(text=prompt, images=pil, return_tensors="pt").to(self.device)
            with torch.inference_mode():
                output_ids = self._model.generate(
                    **inputs, max_new_tokens=160, do_sample=False
                )
            text = self._processor.batch_decode(
                output_ids, skip_special_tokens=True, clean_up_tokenization_spaces=True
            )[0]
            return text.strip() or _fallback_explanation(violations)
        except Exception as exc:  # pragma: no cover
            logger.warning("VLM generation failed (%s); using fallback.", exc)
            return _fallback_explanation(violations)
