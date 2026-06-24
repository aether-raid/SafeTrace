"""MobileSAM mask refinement.

For each YOLO detection box, runs MobileSAM (vit_t) to obtain a tight binary
mask projected back to the original frame coordinates. Falls back gracefully
to the coarse YOLO mask if MobileSAM is unavailable.
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import List, Optional

import numpy as np

from .config import SETTINGS
from .schemas import Detection
from .utils import imread_rgb, resolve_device

logger = logging.getLogger("safetrace.msam")


def _is_disabled_mode(value: str | None) -> bool:
    return (value or "").strip().lower() in {"0", "false", "no", "off", "disabled", "none"}


class MobileSamSegmenter:
    def __init__(
        self,
        checkpoint: str | Path | None = None,
        device: str | None = None,
        model_type: str = "vit_t",
    ) -> None:
        self.device = resolve_device(device or SETTINGS.device)
        self.checkpoint = Path(checkpoint or SETTINGS.mobile_sam_checkpoint)
        self._predictor = None
        self._available = False

        if _is_disabled_mode(getattr(SETTINGS, "mobile_sam_enabled", "auto")):
            logger.info("MobileSAM disabled by configuration.")
            return

        if not self.checkpoint.exists():
            logger.warning(
                "MobileSAM checkpoint missing at %s; refinement disabled.",
                self.checkpoint,
            )
            return
        try:
            from mobile_sam import SamPredictor, sam_model_registry  # type: ignore

            sam = sam_model_registry[model_type](checkpoint=str(self.checkpoint))
            sam.to(device=self.device)
            sam.eval()
            self._predictor = SamPredictor(sam)
            self._available = True
            logger.info("MobileSAM loaded from %s on %s", self.checkpoint, self.device)
        except Exception as exc:  # pragma: no cover - depends on optional dep
            logger.warning("MobileSAM unavailable (%s); using YOLO masks only.", exc)

    # ------------------------------------------------------------------ #
    @property
    def available(self) -> bool:
        return self._available

    def refine(self, image, detections: List[Detection]) -> List[Detection]:
        """Populate ``detection.refined_mask`` for each detection in-place."""
        if not detections:
            return detections
        if not self._available:
            for d in detections:
                if d.refined_mask is None and d.coarse_mask is not None:
                    d.refined_mask = d.coarse_mask
            return detections

        if isinstance(image, (str, Path)):
            img = imread_rgb(image)
        else:
            img = image

        try:
            self._predictor.set_image(img)
        except Exception as exc:  # pragma: no cover
            logger.warning("MobileSAM set_image failed (%s); falling back.", exc)
            for d in detections:
                if d.refined_mask is None and d.coarse_mask is not None:
                    d.refined_mask = d.coarse_mask
            return detections

        h, w = img.shape[:2]
        for det in detections:
            box = np.array(det.bbox, dtype=np.float32)
            try:
                masks, scores, _ = self._predictor.predict(
                    box=box,
                    multimask_output=False,
                )
                if masks is not None and len(masks) > 0:
                    mask = masks[0].astype(bool)
                    if mask.shape != (h, w):
                        # Should already match input, but guard just in case.
                        import cv2
                        mask = cv2.resize(mask.astype(np.uint8), (w, h),
                                          interpolation=cv2.INTER_NEAREST).astype(bool)
                    det.refined_mask = mask
                else:
                    det.refined_mask = det.coarse_mask
            except Exception as exc:  # pragma: no cover
                logger.warning("MobileSAM refine failed for %s: %s", det.label, exc)
                det.refined_mask = det.coarse_mask
        return detections
