"""Rule-based safety violation detection.

Each rule operates on a list of :class:`Detection` objects sharing the same
frame. Masks (refined where possible, otherwise coarse) are compared via IoU
against the configured thresholds.
"""
from __future__ import annotations

import logging
from typing import List, Optional, Sequence

import numpy as np

from .config import SETTINGS
from .schemas import Detection, Violation
from .utils import head_proxy_from_person, mask_iou, torso_proxy_from_person

logger = logging.getLogger("safetrace.rules")


def _mask_of(det: Detection) -> Optional[np.ndarray]:
    return det.refined_mask if det.refined_mask is not None else det.coarse_mask


def _filter(detections: Sequence[Detection], label: str) -> List[Detection]:
    return [d for d in detections if d.label == label]


def _best_person_mask(detections: Sequence[Detection]) -> Optional[np.ndarray]:
    persons = sorted(_filter(detections, "person"), key=lambda d: -d.confidence)
    for p in persons:
        m = _mask_of(p)
        if m is not None and m.any():
            return m
    return None


# --------------------------------------------------------------------------- #
# Individual rules — return a Violation if triggered, else None
# --------------------------------------------------------------------------- #
def rule_helmet_missing(dets: Sequence[Detection]) -> Optional[Violation]:
    heads = _filter(dets, "head")
    person_mask = _best_person_mask(dets) if not heads else None
    head_mask = _mask_of(heads[0]) if heads else (
        head_proxy_from_person(person_mask) if person_mask is not None else None
    )
    if head_mask is None or not head_mask.any():
        return None  # no head/person evidence — cannot evaluate

    helmets = _filter(dets, "helmet")
    best_iou = 0.0
    for hel in helmets:
        iou = mask_iou(head_mask, _mask_of(hel))
        best_iou = max(best_iou, iou)

    if best_iou < SETTINGS.helmet_iou_threshold:
        return Violation(
            name="helmet_missing",
            description="Worker head detected without overlapping helmet.",
            severity="high",
            confidence=1.0 - best_iou,
            evidence={"head_helmet_iou": round(best_iou, 4),
                      "threshold": SETTINGS.helmet_iou_threshold,
                      "helmet_count": len(helmets)},
        )
    return None


def rule_hands_off_wheel(dets: Sequence[Detection]) -> Optional[Violation]:
    hands = _filter(dets, "hand")
    wheels = _filter(dets, "steering_wheel")
    if not hands or not wheels:
        return None
    wheel_mask = _mask_of(wheels[0])
    if wheel_mask is None:
        return None
    best = 0.0
    for h in hands:
        best = max(best, mask_iou(_mask_of(h), wheel_mask))
    if best < SETTINGS.hands_wheel_iou_threshold:
        return Violation(
            name="hands_off_steering_wheel",
            description="No detected hand overlaps the steering wheel.",
            severity="high",
            confidence=1.0 - best,
            evidence={"hand_wheel_iou": round(best, 4),
                      "threshold": SETTINGS.hands_wheel_iou_threshold},
        )
    return None


def rule_phone_use(dets: Sequence[Detection]) -> Optional[Violation]:
    phones = _filter(dets, "phone")
    hands = _filter(dets, "hand")
    if not phones or not hands:
        return None
    best = 0.0
    for p in phones:
        for h in hands:
            best = max(best, mask_iou(_mask_of(p), _mask_of(h)))
    if best > SETTINGS.phone_hand_iou_threshold:
        return Violation(
            name="phone_use",
            description="Phone overlaps with a hand region.",
            severity="medium",
            confidence=best,
            evidence={"phone_hand_iou": round(best, 4),
                      "threshold": SETTINGS.phone_hand_iou_threshold},
        )
    return None


def rule_seatbelt_missing(dets: Sequence[Detection]) -> Optional[Violation]:
    persons = _filter(dets, "person")
    if not persons:
        return None
    person_mask = _best_person_mask(dets)
    torso_dets = _filter(dets, "torso")
    torso_mask = _mask_of(torso_dets[0]) if torso_dets else (
        torso_proxy_from_person(person_mask) if person_mask is not None else None
    )
    if torso_mask is None or not torso_mask.any():
        return None
    belts = _filter(dets, "seatbelt")
    best = 0.0
    for b in belts:
        best = max(best, mask_iou(_mask_of(b), torso_mask))
    if best < SETTINGS.seatbelt_iou_threshold:
        return Violation(
            name="seatbelt_missing",
            description="Person torso detected without an overlapping seatbelt.",
            severity="high",
            confidence=1.0 - best,
            evidence={"seatbelt_torso_iou": round(best, 4),
                      "threshold": SETTINGS.seatbelt_iou_threshold,
                      "seatbelt_count": len(belts)},
        )
    return None


RULES = [
    rule_helmet_missing,
    rule_hands_off_wheel,
    rule_phone_use,
    rule_seatbelt_missing,
]


def evaluate(detections: Sequence[Detection]) -> List[Violation]:
    violations: List[Violation] = []
    for rule in RULES:
        try:
            v = rule(detections)
            if v is not None:
                violations.append(v)
        except Exception as exc:  # pragma: no cover - defensive
            logger.warning("Rule %s failed: %s", rule.__name__, exc)
    return violations
