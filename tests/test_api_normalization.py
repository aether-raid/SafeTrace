from pathlib import Path

from src.api.normalization import normalize_pipeline_results


def test_normalization_creates_frontend_friendly_result(tmp_path):
    annotated = tmp_path / "source_annotated.jpg"
    annotated.write_bytes(b"annotated-image")
    registered = {}

    result = normalize_pipeline_results(
        job_id="job_20260618_123456_abcd",
        media_name="inspection.mp4",
        media_type="video",
        media_size_bytes=1234,
        query="worker without helmet",
        media_dir=tmp_path / "media",
        register_media=lambda filename, path: registered.setdefault(filename, Path(path)),
        raw_frames=[
            {
                "frame_id": "video_20260618_000046",
                "frame_path": "data/frames/video_20260618_000046.jpg",
                "score": 0.059,
                "detections": [{"label": "person", "confidence": 0.9}],
                "violations": [
                    {
                        "name": "helmet_missing",
                        "severity": "high",
                        "confidence": 0.98,
                        "description": "Worker head detected without overlapping helmet.",
                    }
                ],
                "explanation": "A visible worker has no helmet overlap.",
                "annotated_path": str(annotated),
            },
            {
                "frame_id": "video_20260618_000047",
                "frame_path": "data/frames/video_20260618_000047.jpg",
                "score": 0.021,
                "detections": [],
                "violations": [],
                "explanation": None,
                "annotated_path": None,
            },
        ],
    )

    assert result["status"] == "completed"
    assert result["media"]["name"] == "inspection.mp4"
    assert result["media"]["type"] == "video"
    assert result["summary"]["framesAnalyzed"] == 2
    assert result["summary"]["framesWithViolations"] == 1
    assert result["summary"]["highestSeverity"] == "high"
    assert result["summary"]["potentialEventCount"] == 1
    assert result["summary"]["eventTypes"] == ["helmet_missing"]
    assert result["events"][0]["name"] == "Missing Helmet"
    assert result["events"][0]["supportingFrameCount"] == 1
    assert result["violations"][0]["name"] == "Missing Helmet"
    assert result["violations"][0]["confidenceMin"] == 0.98
    assert result["frames"][0]["timestamp"] == "00:00:46"
    assert result["frames"][0]["imageUrl"] == (
        "/api/media/job_20260618_123456_abcd/video_20260618_000046_annotated.jpg"
    )
    assert result["frames"][0]["technicalEvidence"]["detections"][0]["label"] == "person"
    assert result["frames"][1]["imageUrl"] is None
    assert "No annotated evidence image" in result["frames"][1]["imageMessage"]
    assert result["technicalDetails"]["processingMetadata"]["sampledFrameCount"] == 2
    assert result["technicalDetails"]["eventAggregation"]["eventCount"] == 1
    assert list(registered) == ["video_20260618_000046_annotated.jpg"]
    assert registered["video_20260618_000046_annotated.jpg"].read_bytes() == b"annotated-image"
