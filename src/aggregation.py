"""Video-level aggregation for frame/window violation evidence."""
from __future__ import annotations

from collections import defaultdict
from typing import Iterable

from .config import SETTINGS


def _timestamp(frame: dict) -> float:
    if frame.get("timestamp") is not None:
        return float(frame["timestamp"])
    meta = frame.get("metadata") or {}
    if meta.get("timestamp") is not None:
        return float(meta["timestamp"])
    return float(frame.get("frame_index") or meta.get("frame_index") or 0)


def _representative_frames(frames: list[dict], limit: int = 3) -> list[dict]:
    if not frames:
        return []
    ranked = sorted(
        frames,
        key=lambda f: max((v.get("confidence", 0.0) for v in f.get("violations", [])), default=0.0),
        reverse=True,
    )
    reps = []
    seen = set()
    for frame in ranked:
        frame_id = frame.get("frame_id")
        if frame_id in seen:
            continue
        seen.add(frame_id)
        reps.append(
            {
                "frame_id": frame_id,
                "timestamp": _timestamp(frame),
                "frame_path": frame.get("frame_path"),
                "annotated_path": frame.get("annotated_path"),
            }
        )
        if len(reps) >= limit:
            break
    return reps


def _event_status(evidence_count: int) -> str:
    if evidence_count >= SETTINGS.likely_min_evidence_frames:
        return "violation_likely"
    return "review_needed"


def aggregate_video_findings(
    frame_results: Iterable[dict],
    video_id: str,
    vehicle_id: str | None = None,
    seatbelt_grace_seconds: float | None = None,
    merge_gap_seconds: float | None = None,
) -> dict:
    """Collapse frame-level evidence into event-level and video-level findings."""
    grace = SETTINGS.seatbelt_grace_seconds if seatbelt_grace_seconds is None else seatbelt_grace_seconds
    gap = SETTINGS.event_merge_gap_seconds if merge_gap_seconds is None else merge_gap_seconds
    frames = sorted(list(frame_results), key=_timestamp)

    evidence_by_type: dict[str, list[tuple[dict, dict]]] = defaultdict(list)
    for frame in frames:
        ts = _timestamp(frame)
        for violation in frame.get("violations", []):
            vtype = str(violation.get("name") or violation.get("type") or "unknown")
            if vtype == "seatbelt_missing" and ts < grace:
                continue
            evidence_by_type[vtype].append((frame, violation))

    events = []
    for vtype, items in evidence_by_type.items():
        current: list[tuple[dict, dict]] = []
        previous_ts: float | None = None
        for frame, violation in sorted(items, key=lambda item: _timestamp(item[0])):
            ts = _timestamp(frame)
            if current and previous_ts is not None and ts - previous_ts > gap:
                events.append(_build_event(vtype, current))
                current = []
            current.append((frame, violation))
            previous_ts = ts
        if current:
            events.append(_build_event(vtype, current))

    events.sort(key=lambda event: (event["start_time"], event["type"]))
    if any(event["status"] == "violation_likely" for event in events):
        overall_status = "violation_likely"
    elif events:
        overall_status = "review_needed"
    else:
        overall_status = "clear"

    overall_confidence = max((event["confidence"] for event in events), default=0.0)
    return {
        "video_id": video_id,
        "vehicle_id": vehicle_id,
        "overall_status": overall_status,
        "overall_confidence": round(float(overall_confidence), 4),
        "summary": _summary_text(overall_status, events),
        "violations": events,
        "frame_level_evidence_available": bool(frames),
        "frame_evidence_count": sum(len(frame.get("violations", [])) for frame in frames),
    }


def _build_event(vtype: str, items: list[tuple[dict, dict]]) -> dict:
    frames = [frame for frame, _ in items]
    violations = [violation for _, violation in items]
    timestamps = [_timestamp(frame) for frame in frames]
    confidences = [float(v.get("confidence", 0.0)) for v in violations]
    evidence_count = len(items)
    confidence = sum(confidences) / evidence_count if evidence_count else 0.0
    status = _event_status(evidence_count)
    start_time = min(timestamps) if timestamps else 0.0
    end_time = max(timestamps) if timestamps else start_time

    descriptions = [str(v.get("description") or "") for v in violations if v.get("description")]
    return {
        "type": vtype,
        "status": status,
        "confidence": round(float(confidence), 4),
        "start_time": round(float(start_time), 4),
        "end_time": round(float(end_time), 4),
        "duration_seconds": round(float(max(0.0, end_time - start_time)), 4),
        "evidence_frame_count": evidence_count,
        "representative_frames": _representative_frames(frames),
        "reasoning": _event_reasoning(vtype, status, evidence_count, descriptions),
    }


def _event_reasoning(
    vtype: str,
    status: str,
    evidence_count: int,
    descriptions: list[str],
) -> str:
    base = descriptions[0] if descriptions else f"{vtype} was detected."
    if status == "violation_likely":
        return f"{base} Evidence appears in {evidence_count} sampled frames/windows."
    return f"{base} Evidence appears in only {evidence_count} sampled frame/window and needs review."


def _summary_text(status: str, events: list[dict]) -> str:
    if status == "clear":
        return "No sustained safety violations were detected in the sampled timeline."
    likely = [event for event in events if event["status"] == "violation_likely"]
    if likely:
        names = ", ".join(sorted({event["type"] for event in likely}))
        return f"Potential sustained violation detected: {names}."
    names = ", ".join(sorted({event["type"] for event in events}))
    return f"Possible isolated violation evidence detected: {names}."
