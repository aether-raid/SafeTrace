"""Scope guardrails for the optional SafeTrace assistant."""
from __future__ import annotations

import re


SAFETRACE_KEYWORDS = {
    "analysis",
    "analyze",
    "api",
    "assistant",
    "backend",
    "batch",
    "confidence",
    "dashboard",
    "detector",
    "disconnect",
    "disconnected",
    "download",
    "driver",
    "driving",
    "endpoint",
    "endpoints",
    "error",
    "evidence",
    "export",
    "failed",
    "failure",
    "fastapi",
    "file",
    "files",
    "finding",
    "findings",
    "frame",
    "frames",
    "frontend",
    "function",
    "functions",
    "gguf",
    "gpu",
    "helmet",
    "job",
    "json",
    "llama",
    "llama-cpp",
    "llamacpp",
    "limitation",
    "mediasam",
    "mobilesam",
    "model",
    "offline",
    "ollama",
    "packaged",
    "phone",
    "progress",
    "queue",
    "react",
    "reconnect",
    "rejected",
    "report",
    "result",
    "retry",
    "runtime",
    "safe trace",
    "safetrace",
    "seatbelt",
    "stale",
    "statistics",
    "stats",
    "status",
    "stuck",
    "summary",
    "technical",
    "troubleshoot",
    "troubleshooting",
    "upload",
    "video",
    "violation",
    "zip",
}

OUT_OF_SCOPE_PATTERNS = [
    r"\bweather\b",
    r"\bpolitic",
    r"\bstock\b",
    r"\bsports?\b",
    r"\brecipe\b",
    r"\bwrite\s+(?:me\s+)?(?:code|a poem|an essay)\b",
    r"\bgeneral knowledge\b",
]


def is_out_of_scope_question(message: str) -> bool:
    normalized = message.strip().lower()
    return any(re.search(pattern, normalized) for pattern in OUT_OF_SCOPE_PATTERNS)


def is_safetrace_question(message: str, *, has_context: bool = False) -> bool:
    normalized = message.strip().lower()
    if not normalized:
        return False
    if is_out_of_scope_question(normalized):
        return False
    if any(keyword in normalized for keyword in SAFETRACE_KEYWORDS):
        return True
    return has_context and len(normalized.split()) <= 16


def safetrace_refusal() -> str:
    return (
        "I can only answer questions about SafeTrace, SafeTrace analysis results, "
        "evidence frames, backend status, exports, and local assistant configuration."
    )
