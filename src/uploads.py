"""Upload parsing helpers for single media files and bulk ZIPs."""
from __future__ import annotations

import zipfile
from dataclasses import asdict, dataclass
from pathlib import Path, PurePosixPath
from typing import Iterable

IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".bmp", ".webp"}
VIDEO_EXTS = {".mp4", ".mov", ".avi", ".mkv", ".webm"}
ZIP_EXTS = {".zip"}
EXPECTED_ZIP_STRUCTURE = """upload.zip
  Vehicle_A/
    video1.mp4
  Vehicle_B/
    video2.mp4"""


class UploadValidationError(ValueError):
    """User-facing upload validation failure."""


def _is_video(path: str | Path | PurePosixPath) -> bool:
    return Path(str(path)).suffix.lower() in VIDEO_EXTS


def _is_image(path: str | Path | PurePosixPath) -> bool:
    return Path(str(path)).suffix.lower() in IMAGE_EXTS


def is_zip_upload(path: str | Path | PurePosixPath) -> bool:
    return Path(str(path)).suffix.lower() in ZIP_EXTS


def is_supported_upload(path: str | Path | PurePosixPath) -> bool:
    suffix = Path(str(path)).suffix.lower()
    return suffix in VIDEO_EXTS or suffix in IMAGE_EXTS or suffix in ZIP_EXTS


@dataclass
class UploadedMedia:
    batch_id: str
    vehicle_id: str | None
    original_relative_path: str
    filename: str
    stored_path: str
    media_type: str
    status: str = "queued"

    def to_dict(self) -> dict:
        return asdict(self)


def safe_zip_relative_path(name: str) -> PurePosixPath:
    """Return a normalized safe ZIP member path or raise ``ValueError``."""
    normalized = name.replace("\\", "/")
    path = PurePosixPath(normalized)
    if path.is_absolute() or not path.parts:
        raise UploadValidationError(f"Unsafe ZIP path rejected: {name}")
    if any(part in {"", ".", ".."} or ":" in part for part in path.parts):
        raise UploadValidationError(f"Unsafe ZIP path rejected: {name}")
    if len(path.parts) < 2:
        raise UploadValidationError(
            "ZIP videos must live under top-level vehicle folders.\n\n"
            f"Expected structure:\n{EXPECTED_ZIP_STRUCTURE}"
        )
    return path


def ensure_within_directory(root: Path, candidate: Path) -> None:
    root_resolved = root.resolve()
    candidate_resolved = candidate.resolve()
    if root_resolved != candidate_resolved and root_resolved not in candidate_resolved.parents:
        raise UploadValidationError(f"Unsafe extraction target rejected: {candidate}")


def _vehicle_part_index(paths: list[PurePosixPath]) -> int:
    """Return which path segment should be treated as vehicle_id."""
    if not paths:
        return 0
    first_parts = {path.parts[0] for path in paths}
    if len(first_parts) == 1 and all(len(path.parts) >= 3 for path in paths):
        second_parts = {path.parts[1] for path in paths}
        if len(second_parts) > 1:
            return 1
    return 0


def extract_vehicle_zip(
    zip_path: str | Path,
    dest_dir: str | Path,
    batch_id: str,
) -> list[UploadedMedia]:
    """Extract video files from a ZIP whose top-level folders are vehicles."""
    zip_path = Path(zip_path)
    dest_dir = Path(dest_dir)
    dest_dir.mkdir(parents=True, exist_ok=True)
    videos: list[UploadedMedia] = []

    try:
        zf = zipfile.ZipFile(zip_path)
    except zipfile.BadZipFile as exc:
        raise UploadValidationError(f"Uploaded file is not a valid ZIP archive: {zip_path.name}") from exc

    with zf:
        video_members: list[tuple[zipfile.ZipInfo, PurePosixPath]] = []
        for info in zf.infolist():
            if info.is_dir():
                continue
            raw = PurePosixPath(info.filename.replace("\\", "/"))
            if raw.is_absolute() or any(part in {"", ".", ".."} or ":" in part for part in raw.parts):
                raise UploadValidationError(f"Unsafe ZIP path rejected: {info.filename}")
            if not _is_video(raw.name):
                continue
            rel = safe_zip_relative_path(info.filename)
            video_members.append((info, rel))

        vehicle_index = _vehicle_part_index([rel for _, rel in video_members])

        for info, rel in video_members:
            vehicle_id = rel.parts[vehicle_index]
            target = dest_dir.joinpath(*rel.parts)
            ensure_within_directory(dest_dir, target)
            target.parent.mkdir(parents=True, exist_ok=True)
            with zf.open(info) as src, open(target, "wb") as dst:
                dst.write(src.read())
            videos.append(
                UploadedMedia(
                    batch_id=batch_id,
                    vehicle_id=vehicle_id,
                    original_relative_path=str(rel),
                    filename=rel.name,
                    stored_path=str(target),
                    media_type="video",
                )
            )
    if not videos:
        raise UploadValidationError(
            "ZIP upload did not contain any supported video files under vehicle folders.\n\n"
            f"Expected structure:\n{EXPECTED_ZIP_STRUCTURE}"
        )
    return videos


def build_single_media_items(
    paths: Iterable[str | Path],
    batch_id: str,
    vehicle_id: str | None = None,
) -> list[UploadedMedia]:
    """Build metadata records for already-persisted media files."""
    items: list[UploadedMedia] = []
    for path_like in paths:
        path = Path(path_like)
        if _is_video(path):
            media_type = "video"
        elif _is_image(path):
            media_type = "image"
        else:
            continue
        items.append(
            UploadedMedia(
                batch_id=batch_id,
                vehicle_id=vehicle_id,
                original_relative_path=path.name,
                filename=path.name,
                stored_path=str(path),
                media_type=media_type,
            )
        )
    return items
