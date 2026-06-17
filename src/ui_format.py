"""Small presentation helpers shared by the Streamlit UI and tests."""
from __future__ import annotations


def format_evidence_values(evidence: dict | None) -> str:
    """Return compact human-readable evidence key/value text."""
    if not evidence:
        return "No structured evidence values."
    parts = []
    for key, value in evidence.items():
        label = str(key).replace("_", " ")
        if isinstance(value, float):
            rendered = f"{value:.4g}"
        else:
            rendered = str(value)
        parts.append(f"{label}: {rendered}")
    return "; ".join(parts)


def format_confidence_percent(value) -> str:
    """Format a 0..1 confidence value for user-facing display."""
    if value is None:
        return "N/A"
    try:
        percent = float(value) * 100.0
    except (TypeError, ValueError):
        return "N/A"
    if abs(percent - round(percent)) < 1e-9:
        return f"{int(round(percent))}%"
    return f"{percent:.1f}".rstrip("0").rstrip(".") + "%"


def media_status_for_display(item: dict, job_status: str) -> str:
    """Avoid showing stale per-media `queued` while the parent job is active."""
    status = item.get("status") or "queued"
    if job_status in {"processing", "completed", "failed"} and status == "queued":
        return job_status
    return status


def current_media_text(job: dict) -> str:
    """Describe the current media scope without inventing per-video progress."""
    media = job.get("media") or []
    if job.get("current_media"):
        return str(job["current_media"])
    if job.get("status") != "processing" or not media:
        return ""
    if len(media) == 1:
        return str(media[0].get("filename") or media[0].get("original_relative_path") or "")
    return f"Processing batch of {len(media)} media files"
