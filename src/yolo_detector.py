"""YOLO segmentation wrapper (Ultralytics).

Default checkpoint is YOLOv9-seg, with an optional fallback to YOLOv8-seg.
Returns a normalized list of :class:`Detection` objects with coarse masks
projected back to the original frame size.
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import List, Optional

import cv2
import numpy as np

from .config import SETTINGS, normalize_label
from .detector_utils import resolve_detector_checkpoint
from .schemas import Detection
from .utils import imread_rgb, resolve_device

logger = logging.getLogger("safetrace.yolo")


class YoloDetector:
    def __init__(
        self,
        checkpoint: str | Path | None = None,
        fallback_checkpoint: str | Path | None = None,
        device: str | None = None,
        conf: float | None = None,
        iou: float | None = None,
    ) -> None:
        from ultralytics import YOLO  # local import to avoid hard dep at import time

        self.device = resolve_device(device or SETTINGS.device)
        self.conf = conf if conf is not None else SETTINGS.yolo_conf_threshold
        self.iou = iou if iou is not None else SETTINGS.yolo_iou_threshold

        custom = None if checkpoint is not None else SETTINGS.custom_detector_weights
        chosen = resolve_detector_checkpoint(
            custom_checkpoint=custom,
            default_checkpoint=checkpoint or SETTINGS.yolo_checkpoint,
            fallback_checkpoint=fallback_checkpoint or SETTINGS.yolo_fallback_checkpoint,
        )

        logger.info("Loading YOLO model %s on %s", chosen, self.device)
        self.model = YOLO(str(chosen))
        self.checkpoint = chosen
        # Cache the names dict (Ultralytics returns id->name)
        self.names = self.model.names if hasattr(self.model, "names") else {}

    # ------------------------------------------------------------------ #
    def detect(self, image: str | Path | np.ndarray) -> List[Detection]:
        if isinstance(image, (str, Path)):
            img = imread_rgb(image)
        else:
            img = image
        h, w = img.shape[:2]

        # Ultralytics expects BGR or PIL; passing RGB ndarray works too via PIL conversion.
        results = self.model.predict(
            source=img[:, :, ::-1],  # to BGR for cv2-based loader
            conf=self.conf,
            iou=self.iou,
            device=0 if self.device == "cuda" else "cpu",
            verbose=False,
        )
        if not results:
            return []
        r = results[0]

        boxes = getattr(r, "boxes", None)
        masks = getattr(r, "masks", None)
        names = getattr(r, "names", self.names) or {}
        if boxes is None or len(boxes) == 0:
            return []

        xyxy = boxes.xyxy.detach().cpu().numpy()
        confs = boxes.conf.detach().cpu().numpy()
        cls_ids = boxes.cls.detach().cpu().numpy().astype(int)

        # masks.data is (N, Hm, Wm) at model input resolution; resize per-instance.
        mask_arrs: Optional[np.ndarray] = None
        if masks is not None and getattr(masks, "data", None) is not None:
            mask_arrs = masks.data.detach().cpu().numpy()

        detections: List[Detection] = []
        for i in range(len(xyxy)):
            raw = str(names.get(int(cls_ids[i]), str(cls_ids[i])))
            canonical = normalize_label(raw, class_id=int(cls_ids[i]))
            label = canonical or raw

            coarse: Optional[np.ndarray] = None
            if mask_arrs is not None and i < len(mask_arrs):
                m = mask_arrs[i]
                if m.shape[:2] != (h, w):
                    m = cv2.resize(m.astype(np.float32), (w, h),
                                   interpolation=cv2.INTER_NEAREST)
                coarse = m.astype(bool)

            detections.append(
                Detection(
                    label=label,
                    raw_label=raw,
                    confidence=float(confs[i]),
                    bbox=[float(v) for v in xyxy[i].tolist()],
                    coarse_mask=coarse,
                )
            )
        return detections
