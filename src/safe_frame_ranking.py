"""Lightweight Safe Mode frame ranking without semantic embeddings."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Sequence

from src.schemas import Detection, Violation


INTENT_LABELS: dict[str, set[str]] = {
    "seatbelt": {"person", "torso", "seatbelt", "hand", "steering_wheel", "driver"},
    "phone": {"person", "hand", "phone", "steering_wheel", "driver"},
    "helmet": {"person", "head", "helmet", "worker"},
    "person": {"person", "head", "torso", "hand", "worker", "driver"},
    "machinery": {"machinery", "machine", "equipment", "forklift", "truck", "vehicle"},
    "fall": {"person", "worker"},
    "damage": {"damage", "damaged", "broken", "crack", "equipment", "machinery", "vehicle"},
}
INTENT_KEYWORDS: dict[str, tuple[str, ...]] = {
    "seatbelt": ("seatbelt", "seat belt", "belt"),
    "phone": ("phone", "mobile phone", "cell phone", "smartphone"),
    "helmet": ("helmet", "hardhat", "hard hat"),
    "person": ("person", "worker", "driver", "operator", "employee"),
    "machinery": ("machinery", "machine", "equipment", "forklift", "excavator", "loader"),
    "fall": ("fall", "falling", "fallen", "slip", "trip"),
    "damage": ("damage", "damaged", "broken", "crack", "defect"),
}
HUMAN_LABELS = {"person", "head", "torso", "hand"}
INTERIOR_LABELS = {"steering_wheel", "seatbelt", "torso", "hand", "driver"}
ROAD_ONLY_LABELS = {
    "car",
    "truck",
    "bus",
    "traffic light",
    "traffic sign",
    "road",
    "lane",
    "vehicle",
    "motorcycle",
}


@dataclass(frozen=True)
class QueryIntent:
    intents: tuple[str, ...]
    relevant_labels: tuple[str, ...]
    raw_query: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "intents": list(self.intents),
            "relevantLabels": list(self.relevant_labels),
            "rawQuery": self.raw_query,
        }


@dataclass
class RankedFrameCandidate:
    frame_path: Path
    frame_index: int
    total_frames: int
    detections: list[Detection]
    violations: list[Violation]
    query_intent: QueryIntent
    raw_score: float
    normalized_score: float
    reasons: list[str]
    detection_summary: dict[str, Any]
    selected_for: str = "query_relevance"

    @property
    def ranking_reason(self) -> str:
        return "; ".join(self.reasons[:3]) if self.reasons else "Selected for temporal coverage."

    def search_metadata(self, *, rank: int) -> dict[str, Any]:
        return {
            "mode": "safe_ranked_frame_scan",
            "semanticSearch": False,
            "embeddingBypassed": True,
            "frameRankingScore": round(self.raw_score, 4),
            "normalizedFrameScore": round(self.normalized_score, 4),
            "rankingReason": self.ranking_reason,
            "rankingReasons": list(self.reasons),
            "queryIntent": self.query_intent.to_dict(),
            "detectedObjectSummary": self.detection_summary,
            "selectedFor": self.selected_for,
            "selectionRank": rank,
            "sourceFrameIndex": self.frame_index,
            "sourceFrameCount": self.total_frames,
        }


def parse_query_intent(query: str) -> QueryIntent:
    normalized = f" {(query or '').strip().lower()} "
    intents: list[str] = []
    relevant: set[str] = set()
    for intent, keywords in INTENT_KEYWORDS.items():
        if any(f" {keyword} " in normalized or keyword in normalized for keyword in keywords):
            intents.append(intent)
            relevant.update(INTENT_LABELS[intent])
    if not intents:
        intents.append("person")
        relevant.update(INTENT_LABELS["person"])
    return QueryIntent(
        intents=tuple(dict.fromkeys(intents)),
        relevant_labels=tuple(sorted(relevant)),
        raw_query=query or "",
    )


def score_frame_for_safe_mode(
    *,
    frame_path: Path,
    frame_index: int,
    total_frames: int,
    detections: Sequence[Detection],
    violations: Sequence[Violation],
    query_intent: QueryIntent,
    image_shape: tuple[int, int] | tuple[int, int, int] | None = None,
) -> RankedFrameCandidate:
    labels = [_label(det) for det in detections]
    label_set = set(labels)
    relevant = set(query_intent.relevant_labels)
    score = 0.0
    reasons: list[str] = []
    detection_summary = summarize_detections(detections, image_shape=image_shape)

    if violations:
        score += 12.0 + min(len(violations), 3) * 1.5
        reasons.append("violation candidate was found")

    if label_set & HUMAN_LABELS:
        score += 4.0
        reasons.append("person or body evidence was detected")
    if label_set & {"torso", "hand", "head"}:
        score += 2.0
        reasons.append("body-part evidence supports the query")
    if label_set & INTERIOR_LABELS and ("seatbelt" in query_intent.intents or "phone" in query_intent.intents):
        score += 3.0
        reasons.append("driver-cabin evidence matched the query intent")

    matched_relevant = sorted(label_set & relevant)
    if matched_relevant:
        score += 2.5 + min(len(matched_relevant), 4) * 0.75
        reasons.append(f"query-related objects detected: {', '.join(matched_relevant[:5])}")

    largest_relevant_area = detection_summary.get("largestRelevantAreaFraction") or 0.0
    if largest_relevant_area >= 0.08:
        score += min(largest_relevant_area * 10.0, 2.5)
        reasons.append("large relevant subject in frame")

    if _is_road_only(label_set):
        score -= 4.0
        reasons.append("road-only or distant-vehicle frame deprioritized")
    elif not detections:
        score -= 1.5
        reasons.append("no relevant objects detected")
    elif not matched_relevant and not violations:
        score -= 1.0
        reasons.append("objects did not match query intent")

    normalized = max(0.0, min(score / 16.0, 1.0))
    return RankedFrameCandidate(
        frame_path=frame_path,
        frame_index=frame_index,
        total_frames=total_frames,
        detections=list(detections),
        violations=list(violations),
        query_intent=query_intent,
        raw_score=score,
        normalized_score=normalized,
        reasons=_dedupe_reasons(reasons),
        detection_summary=detection_summary,
    )


def select_ranked_frames(
    candidates: Sequence[RankedFrameCandidate],
    *,
    top_k: int,
) -> list[RankedFrameCandidate]:
    if not candidates or top_k <= 0:
        return []
    remaining = list(candidates)
    selected: list[RankedFrameCandidate] = []

    def pop_best_violation() -> RankedFrameCandidate | None:
        violation_candidates = [item for item in remaining if item.violations]
        if not violation_candidates:
            return None
        return max(violation_candidates, key=lambda item: (item.raw_score, item.frame_index))

    while len(selected) < top_k:
        candidate = pop_best_violation()
        if candidate is None:
            break
        candidate.selected_for = "violation_evidence"
        selected.append(candidate)
        remaining.remove(candidate)

    while remaining and len(selected) < top_k:
        candidate = max(
            remaining,
            key=lambda item: (
                item.raw_score + _temporal_diversity_bonus(item, selected),
                _temporal_dispersal(item),
                -item.frame_index,
            ),
        )
        if candidate.raw_score <= 0 and not candidate.violations:
            candidate.selected_for = "temporal_diversity"
            if not candidate.reasons:
                candidate.reasons.append("selected for temporal coverage")
        else:
            candidate.selected_for = "query_relevance"
        selected.append(candidate)
        remaining.remove(candidate)

    return selected


def summarize_detections(
    detections: Sequence[Detection],
    *,
    image_shape: tuple[int, int] | tuple[int, int, int] | None = None,
) -> dict[str, Any]:
    counts: dict[str, int] = {}
    confidences: dict[str, float] = {}
    largest_area = 0.0
    largest_relevant_area = 0.0
    for det in detections:
        label = _label(det)
        counts[label] = counts.get(label, 0) + 1
        confidences[label] = max(confidences.get(label, 0.0), float(det.confidence or 0.0))
        area = _bbox_area_fraction(det, image_shape)
        largest_area = max(largest_area, area)
        if label in HUMAN_LABELS or label in INTERIOR_LABELS:
            largest_relevant_area = max(largest_relevant_area, area)
    return {
        "labels": sorted(counts),
        "counts": counts,
        "maxConfidenceByLabel": {key: round(value, 4) for key, value in sorted(confidences.items())},
        "objectCount": len(detections),
        "largestObjectAreaFraction": round(largest_area, 4),
        "largestRelevantAreaFraction": round(largest_relevant_area, 4),
    }


def _label(det: Detection) -> str:
    return str(det.label or det.raw_label or "unknown").strip().lower()


def _bbox_area_fraction(
    det: Detection,
    image_shape: tuple[int, int] | tuple[int, int, int] | None,
) -> float:
    if not image_shape or len(image_shape) < 2:
        return 0.0
    height = float(image_shape[0] or 0)
    width = float(image_shape[1] or 0)
    if width <= 0 or height <= 0:
        return 0.0
    try:
        x1, y1, x2, y2 = [float(value) for value in det.bbox[:4]]
    except (TypeError, ValueError):
        return 0.0
    return max(0.0, x2 - x1) * max(0.0, y2 - y1) / (width * height)


def _is_road_only(labels: set[str]) -> bool:
    if not labels:
        return False
    return bool(labels) and labels <= ROAD_ONLY_LABELS


def _temporal_diversity_bonus(
    candidate: RankedFrameCandidate,
    selected: Sequence[RankedFrameCandidate],
) -> float:
    if not selected or candidate.total_frames <= 1:
        return 0.0
    nearest_distance = min(abs(candidate.frame_index - item.frame_index) for item in selected)
    return min(nearest_distance / max(candidate.total_frames - 1, 1), 1.0) * 3.0


def _temporal_dispersal(candidate: RankedFrameCandidate) -> float:
    if candidate.total_frames <= 1:
        return 0.0
    middle = (candidate.total_frames - 1) / 2.0
    return abs(candidate.frame_index - middle) / max(middle, 1.0)


def _dedupe_reasons(reasons: Iterable[str]) -> list[str]:
    seen: set[str] = set()
    output: list[str] = []
    for reason in reasons:
        if reason in seen:
            continue
        seen.add(reason)
        output.append(reason)
    return output
