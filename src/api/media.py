"""Safe media serving helpers for API job artifacts."""
from __future__ import annotations

from pathlib import Path, PurePosixPath

from .jobs import JobRecord

IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".webp", ".bmp"}


def resolve_job_media_path(record: JobRecord, filename: str) -> Path | None:
    path_name = PurePosixPath(filename)
    if path_name.name != filename or ".." in path_name.parts:
        return None
    if Path(filename).suffix.lower() not in IMAGE_SUFFIXES:
        return None

    path = record.media_files.get(filename)
    if path is None:
        return None

    resolved = path.resolve()
    output_root = record.output_dir.resolve()
    if output_root not in resolved.parents and resolved != output_root:
        return None
    if not resolved.exists() or not resolved.is_file():
        return None
    return resolved

