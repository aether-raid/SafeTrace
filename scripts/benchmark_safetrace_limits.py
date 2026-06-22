"""Summarize SafeTrace API job manifests without running model inference.

This script is intentionally lightweight. It inspects persisted API job
manifests and reports timing, status, and input-size information so local runs
can be compared before and after backend hardening changes.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Dict, Iterable, List


def load_manifests(jobs_root: Path) -> List[Dict[str, Any]]:
    manifests: List[Dict[str, Any]] = []
    if not jobs_root.exists():
        return manifests
    for manifest_path in sorted(jobs_root.glob("*/manifest.json")):
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        manifest["_manifestPath"] = str(manifest_path)
        manifests.append(manifest)
    return manifests


def summarize(manifests: Iterable[Dict[str, Any]]) -> Dict[str, Any]:
    rows = list(manifests)
    status_counts: Dict[str, int] = {}
    total_input_bytes = 0
    completed_durations = []
    event_counts = []
    sampled_frame_counts = []

    for manifest in rows:
        status = str(manifest.get("status") or "unknown")
        status_counts[status] = status_counts.get(status, 0) + 1
        input_meta = dict(manifest.get("input") or {})
        total_input_bytes += int(input_meta.get("sizeBytes") or 0)
        metrics = dict(manifest.get("metrics") or {})
        duration = metrics.get("totalWallClockSeconds")
        if duration is not None and status == "completed":
            completed_durations.append(float(duration))
        result_path = dict(manifest.get("output") or {}).get("resultPath")
        manifest_path = Path(str(manifest.get("_manifestPath") or ""))
        if result_path and manifest_path:
            try:
                result = json.loads((manifest_path.parent / str(result_path)).read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                result = {}
            summary = dict(result.get("summary") or {})
            technical = dict(result.get("technicalDetails") or {})
            processing = dict(technical.get("processingMetadata") or {})
            if summary.get("potentialEventCount") is not None:
                event_counts.append(int(summary["potentialEventCount"]))
            if processing.get("sampledFrameCount") is not None:
                sampled_frame_counts.append(int(processing["sampledFrameCount"]))

    return {
        "jobCount": len(rows),
        "statusCounts": status_counts,
        "totalInputBytes": total_input_bytes,
        "completedDurationSeconds": {
            "count": len(completed_durations),
            "min": min(completed_durations) if completed_durations else None,
            "max": max(completed_durations) if completed_durations else None,
            "avg": (sum(completed_durations) / len(completed_durations)) if completed_durations else None,
        },
        "eventCounts": {
            "count": len(event_counts),
            "max": max(event_counts) if event_counts else None,
            "avg": (sum(event_counts) / len(event_counts)) if event_counts else None,
        },
        "sampledFrameCounts": {
            "count": len(sampled_frame_counts),
            "max": max(sampled_frame_counts) if sampled_frame_counts else None,
            "avg": (sum(sampled_frame_counts) / len(sampled_frame_counts)) if sampled_frame_counts else None,
        },
    }


def print_table(manifests: List[Dict[str, Any]]) -> None:
    if not manifests:
        print("No job manifests found.")
        return

    headers = ["jobId", "status", "inputBytes", "mediaType", "durationSeconds", "updatedAt"]
    print(" | ".join(headers))
    print(" | ".join("-" * len(header) for header in headers))
    for manifest in manifests:
        input_meta = dict(manifest.get("input") or {})
        metrics = dict(manifest.get("metrics") or {})
        values = [
            str(manifest.get("jobId") or ""),
            str(manifest.get("status") or ""),
            str(input_meta.get("sizeBytes") or 0),
            str(input_meta.get("mediaType") or ""),
            "" if metrics.get("totalWallClockSeconds") is None else f"{float(metrics['totalWallClockSeconds']):.3f}",
            str(manifest.get("updatedAt") or ""),
        ]
        print(" | ".join(values))


def main() -> int:
    parser = argparse.ArgumentParser(description="Summarize SafeTrace API job manifests.")
    parser.add_argument(
        "--jobs-root",
        type=Path,
        default=Path("data") / "api_jobs",
        help="Directory containing persisted API job directories.",
    )
    parser.add_argument("--json", action="store_true", help="Print JSON summary instead of a table.")
    args = parser.parse_args()

    manifests = load_manifests(args.jobs_root)
    if args.json:
        print(json.dumps(summarize(manifests), indent=2, sort_keys=True))
    else:
        print_table(manifests)
        print()
        print(json.dumps(summarize(manifests), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
