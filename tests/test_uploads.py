import zipfile

import pytest

from src.uploads import (
    EXPECTED_ZIP_STRUCTURE,
    UploadValidationError,
    build_single_media_items,
    extract_vehicle_zip,
    is_supported_upload,
    is_zip_upload,
    safe_zip_relative_path,
)


def test_zip_is_supported_upload_type():
    assert is_zip_upload("drivers.zip")
    assert is_supported_upload("drivers.zip")
    assert is_supported_upload("clip.mp4")
    assert is_supported_upload("clip.avi")
    assert is_supported_upload("clip.mov")
    assert is_supported_upload("clip.mkv")


def test_bulk_zip_vehicle_folder_becomes_vehicle_id(workspace_tmp):
    zip_path = workspace_tmp / "upload.zip"
    with zipfile.ZipFile(zip_path, "w") as zf:
        zf.writestr("Vehicle_A/video1.mp4", b"video")
        zf.writestr("Vehicle_A/notes.txt", b"ignore me")
        zf.writestr("Vehicle_B/nested/video2.mov", b"video")

    items = extract_vehicle_zip(zip_path, workspace_tmp / "out", batch_id="batch_1")

    assert [item.vehicle_id for item in items] == ["Vehicle_A", "Vehicle_B"]
    assert items[0].original_relative_path == "Vehicle_A/video1.mp4"
    assert items[1].filename == "video2.mov"


def test_zip_single_outer_folder_uses_inner_vehicle_folders(workspace_tmp):
    zip_path = workspace_tmp / "upload.zip"
    with zipfile.ZipFile(zip_path, "w") as zf:
        zf.writestr("test upload/Vehicle A/a.mp4", b"video")
        zf.writestr("test upload/Vehicle B/b.mp4", b"video")

    items = extract_vehicle_zip(zip_path, workspace_tmp / "out", batch_id="batch_1")

    assert [item.vehicle_id for item in items] == ["Vehicle A", "Vehicle B"]
    assert items[0].original_relative_path == "test upload/Vehicle A/a.mp4"


def test_unsafe_zip_paths_are_rejected():
    with pytest.raises(UploadValidationError, match="Unsafe ZIP path"):
        safe_zip_relative_path("../evil.mp4")


def test_video_at_zip_root_is_rejected(workspace_tmp):
    zip_path = workspace_tmp / "upload.zip"
    with zipfile.ZipFile(zip_path, "w") as zf:
        zf.writestr("video1.mp4", b"video")

    with pytest.raises(UploadValidationError, match="top-level vehicle folders"):
        extract_vehicle_zip(zip_path, workspace_tmp / "out", batch_id="batch_1")


def test_zip_with_no_valid_videos_returns_useful_error(workspace_tmp):
    zip_path = workspace_tmp / "upload.zip"
    with zipfile.ZipFile(zip_path, "w") as zf:
        zf.writestr("Vehicle_A/readme.txt", b"ignore me")

    with pytest.raises(UploadValidationError) as excinfo:
        extract_vehicle_zip(zip_path, workspace_tmp / "out", batch_id="batch_1")

    assert "did not contain any supported video files" in str(excinfo.value)
    assert EXPECTED_ZIP_STRUCTURE in str(excinfo.value)


def test_invalid_zip_file_returns_useful_error(workspace_tmp):
    zip_path = workspace_tmp / "upload.zip"
    zip_path.write_text("not really a zip", encoding="utf-8")

    with pytest.raises(UploadValidationError, match="not a valid ZIP archive"):
        extract_vehicle_zip(zip_path, workspace_tmp / "out", batch_id="batch_1")


def test_single_video_upload_metadata_still_works(workspace_tmp):
    video_path = workspace_tmp / "single.mp4"
    video_path.write_bytes(b"video")

    items = build_single_media_items([video_path], batch_id="batch_1")

    assert len(items) == 1
    assert items[0].filename == "single.mp4"
    assert items[0].media_type == "video"
    assert items[0].vehicle_id is None
