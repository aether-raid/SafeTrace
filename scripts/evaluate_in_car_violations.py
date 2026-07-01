"""Evaluate SafeTrace in-car violation result coverage from local sample outputs.

This script intentionally does not train, download, or modify any model assets.
By default it reads normalized SafeTrace result JSON files from --samples-dir and
reports whether current outputs contain in-car violation evidence. If no sample
outputs are present, it exits successfully with NOT_TESTED_NO_SAMPLE.
"""
from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable


STATUSES = {"PASS", "FAIL", "UNSUPPORTED", "NOT_TESTED_NO_SAMPLE"}


@dataclass(frozen=True)
class Capability:
    key: str
    label: str
    violation_names: tuple[str, ...]
    detector_dependency: str


CAPABILITIES = (
    Capability(
        key="missing_seatbelt",
        label="Missing seatbelt",
        violation_names=("seatbelt_missing", "Missing Seatbelt"),
        detector_dependency="Requires person/torso and seatbelt detections or masks.",
    ),
    Capability(
        key="phone_usage_while_driving",
        label="Phone usage while driving",
        violation_names=("phone_use", "Phone Use"),
        detector_dependency="Requires phone and hand detections or masks.",
    ),
    Capability(
        key="missing_helmet",
        label="Missing helmet",
        violation_names=("helmet_missing", "Missing Helmet"),
        detector_dependency="Requires person/head and helmet detections or masks.",
    ),
)


@dataclass
class CapabilityResult:
    key: str
    label: str
    status: str
    evidence_files: list[str]
    reason: str
    detector_dependency: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "key": self.key,
            "label": self.label,
            "status": self.status,
            "evidenceFiles": self.evidence_files,
            "reason": self.reason,
            "detectorDependency": self.detector_dependency,
        }


def _normalized_name(value: Any) -> str:
    return str(value or "").strip().lower().replace(" ", "_").replace("-", "_")


def _iter_violations(payload: dict[str, Any]) -> Iterable[str]:
    for violation in payload.get("violations") or []:
        yield str(violation.get("id") or violation.get("name") or "")
    for event in payload.get("events") or []:
        yield str(event.get("type") or event.get("name") or "")
    for frame in payload.get("frames") or []:
        for violation in frame.get("violations") or []:
            yield str(violation.get("id") or violation.get("type") or violation.get("name") or "")


def _payload_has_capability(payload: dict[str, Any], capability: Capability) -> bool:
    expected = {_normalized_name(name) for name in capability.violation_names}
    return any(_normalized_name(name) in expected for name in _iter_violations(payload))


def load_sample_payloads(samples_dir: Path) -> list[tuple[Path, dict[str, Any]]]:
    if not samples_dir.exists() or not samples_dir.is_dir():
        return []
    payloads: list[tuple[Path, dict[str, Any]]] = []
    for path in sorted(samples_dir.rglob("*.json")):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if isinstance(payload, dict):
            payloads.append((path, payload))
    return payloads


def evaluate_capabilities(samples_dir: Path) -> list[CapabilityResult]:
    payloads = load_sample_payloads(samples_dir)
    if not payloads:
        return [
            CapabilityResult(
                key=capability.key,
                label=capability.label,
                status="NOT_TESTED_NO_SAMPLE",
                evidence_files=[],
                reason=(
                    "No normalized SafeTrace result JSON files were found. Add local manual evaluation "
                    "outputs under the samples directory before claiming capability support."
                ),
                detector_dependency=capability.detector_dependency,
            )
            for capability in CAPABILITIES
        ]

    results: list[CapabilityResult] = []
    for capability in CAPABILITIES:
        evidence = [
            str(path)
            for path, payload in payloads
            if _payload_has_capability(payload, capability)
        ]
        if evidence:
            status = "PASS"
            reason = "At least one supplied SafeTrace result JSON contains this violation output."
        else:
            status = "UNSUPPORTED"
            reason = (
                "The supplied SafeTrace result JSON files did not contain this violation output. "
                "This is not a detector benchmark failure unless the samples include labeled ground truth."
            )
        results.append(
            CapabilityResult(
                key=capability.key,
                label=capability.label,
                status=status,
                evidence_files=evidence,
                reason=reason,
                detector_dependency=capability.detector_dependency,
            )
        )
    return results


def render_text(results: list[CapabilityResult]) -> str:
    lines = [
        "SafeTrace in-car violation capability evaluation",
        "Status values: PASS, FAIL, UNSUPPORTED, NOT_TESTED_NO_SAMPLE",
        "",
    ]
    for result in results:
        lines.append(f"{result.key}: {result.status}")
        lines.append(f"  label: {result.label}")
        lines.append(f"  reason: {result.reason}")
        lines.append(f"  detector dependency: {result.detector_dependency}")
        if result.evidence_files:
            lines.append(f"  evidence files: {', '.join(result.evidence_files)}")
        lines.append("")
    return "\n".join(lines).rstrip()


def main() -> int:
    parser = argparse.ArgumentParser(description="Evaluate in-car SafeTrace violation result coverage.")
    parser.add_argument("--samples-dir", default="data/manual_eval", help="Directory containing normalized result JSON files.")
    parser.add_argument("--format", choices=("text", "json"), default="text", help="Output format.")
    args = parser.parse_args()

    samples_dir = Path(args.samples_dir)
    results = evaluate_capabilities(samples_dir)
    payload = {
        "samplesDir": str(samples_dir),
        "results": [result.to_dict() for result in results],
    }
    if args.format == "json":
        print(json.dumps(payload, indent=2))
    else:
        print(render_text(results))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
