import numpy as np

from src.preprocessing import build_frame_windows, pool_embeddings


def test_pool_embeddings_supports_mean_and_max(tmp_path):
    frame_paths = [tmp_path / f"frame_{index:03d}.jpg" for index in range(3)]
    windows = build_frame_windows(frame_paths, window_size=3)
    embeddings = np.array(
        [
            [1.0, 0.0],
            [0.0, 0.2],
            [0.2, 0.0],
        ],
        dtype=np.float32,
    )

    mean_pooled = pool_embeddings(embeddings, windows, strategy="mean")
    max_pooled = pool_embeddings(embeddings, windows, strategy="max")

    assert mean_pooled.shape == (1, 2)
    assert max_pooled.shape == (1, 2)
    assert not np.allclose(mean_pooled, max_pooled)
    assert np.isclose(np.linalg.norm(mean_pooled[0]), 1.0)
    assert np.isclose(np.linalg.norm(max_pooled[0]), 1.0)


def test_pool_embeddings_rejects_unsupported_strategy(tmp_path):
    frame_paths = [tmp_path / "frame.jpg"]
    windows = build_frame_windows(frame_paths)
    embeddings = np.array([[1.0, 0.0]], dtype=np.float32)

    try:
        pool_embeddings(embeddings, windows, strategy="attention")
    except ValueError as exc:
        assert "Unsupported pooling strategy" in str(exc)
    else:
        raise AssertionError("Unsupported pooling strategy should fail explicitly")
