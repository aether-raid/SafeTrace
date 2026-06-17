import numpy as np

from src.preprocessing import build_frame_windows, pool_window_embeddings, sampling_step


def _records(count):
    return [
        {
            "frame_id": f"frame_{i}",
            "frame_path": f"/tmp/frame_{i}.jpg",
            "frame_index": i * 30,
            "timestamp": float(i),
            "video_id": "video_a",
            "vehicle_id": "Vehicle_A",
        }
        for i in range(count)
    ]


def test_sampling_step_respects_target_fps():
    assert sampling_step(30.0, 1.0) == 30
    assert sampling_step(30.0, 15.0) == 2
    assert sampling_step(5.0, 30.0) == 1


def test_window_metadata_contains_frame_indices_and_timestamps():
    windows = build_frame_windows(_records(5), window_size=3, stride=2)

    assert len(windows) == 2
    assert windows[0]["window_frame_indices"] == [0, 30, 60]
    assert windows[0]["window_timestamps"] == [0.0, 1.0, 2.0]
    assert windows[0]["vehicle_id"] == "Vehicle_A"
    assert windows[1]["window_frame_indices"] == [60, 90, 120]


def test_window_embedding_mean_pool_shape_and_values():
    embeddings = np.array(
        [
            [1.0, 0.0],
            [1.0, 0.0],
            [0.0, 1.0],
            [0.0, 1.0],
        ],
        dtype=np.float32,
    )
    windows = build_frame_windows(_records(4), window_size=2, stride=2)

    pooled = pool_window_embeddings(embeddings, windows)

    assert pooled.shape == (2, 2)
    np.testing.assert_allclose(pooled[0], [1.0, 0.0])
    np.testing.assert_allclose(pooled[1], [0.0, 1.0])
