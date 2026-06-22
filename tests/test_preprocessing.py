import cv2
import numpy as np

from src.preprocessing import build_frame_windows
from src.utils import extract_frames_with_metadata


def test_extract_frames_records_sampling_metadata(tmp_path):
    video_path = tmp_path / "tiny.mp4"
    writer = cv2.VideoWriter(
        str(video_path),
        cv2.VideoWriter_fourcc(*"mp4v"),
        4.0,
        (16, 16),
    )
    for index in range(8):
        frame = np.full((16, 16, 3), index * 20, dtype=np.uint8)
        writer.write(frame)
    writer.release()

    frames, metadata = extract_frames_with_metadata(video_path, tmp_path / "frames", fps=2.0, max_frames=3)

    assert len(frames) == 3
    assert metadata["samplingStrategy"] == "fixed_fps"
    assert metadata["sampledFrameCount"] == 3
    assert metadata["sourceVideoFrameCount"] == 8
    assert metadata["sourceVideoDurationSeconds"] == 2.0
    assert metadata["frameStep"] == 2


def test_build_frame_windows_groups_multiple_frames_without_changing_defaults(tmp_path):
    frame_paths = [tmp_path / f"frame_{index:03d}.jpg" for index in range(5)]

    default_windows = build_frame_windows(frame_paths)
    grouped_windows = build_frame_windows(frame_paths, window_size=3, stride=2)

    assert len(default_windows) == 5
    assert default_windows[0].frame_indices == [0]
    assert len(grouped_windows) == 2
    assert grouped_windows[0].frame_indices == [0, 1, 2]
    assert grouped_windows[1].frame_indices == [2, 3, 4]
