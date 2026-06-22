from src.aggregation import aggregate_violation_events, summarize_events


def frame(frame_id, frame_number, timestamp, violation_type="helmet_missing", confidence=0.8):
    return {
        "id": frame_id,
        "frameNumber": frame_number,
        "timestamp": timestamp,
        "imageUrl": f"/api/media/job/{frame_id}.jpg",
        "violations": [
            {
                "id": violation_type,
                "name": violation_type.replace("_", " ").title(),
                "severity": "high",
                "description": "Frame-level finding",
                "confidence": confidence,
            }
        ],
    }


def test_nearby_repeated_frame_findings_are_grouped_into_one_event():
    events = aggregate_violation_events(
        [
            frame("f1", 1, "00:00:10", confidence=0.6),
            frame("f2", 2, "00:00:12", confidence=0.8),
            frame("f3", 3, "00:00:14", confidence=0.7),
        ],
        merge_gap_seconds=5,
    )

    assert len(events) == 1
    assert events[0]["type"] == "helmet_missing"
    assert events[0]["startTimestamp"] == "00:00:10"
    assert events[0]["endTimestamp"] == "00:00:14"
    assert events[0]["supportingFrameCount"] == 3
    assert round(events[0]["representativeConfidence"], 2) == 0.7


def test_distant_or_different_violation_findings_create_separate_events():
    events = aggregate_violation_events(
        [
            frame("f1", 1, "00:00:10", "helmet_missing"),
            frame("f2", 2, "00:00:30", "helmet_missing"),
            frame("f3", 3, "00:00:31", "phone_use"),
        ],
        merge_gap_seconds=5,
    )

    assert len(events) == 3
    assert {event["type"] for event in events} == {"helmet_missing", "phone_use"}


def test_event_summary_reports_video_level_confidence_and_key_events():
    events = aggregate_violation_events(
        [
            frame("f1", 1, "00:00:10", confidence=0.5),
            frame("f2", 2, "00:00:11", confidence=0.9),
        ],
        merge_gap_seconds=5,
    )

    summary = summarize_events(events)

    assert summary["potentialEventCount"] == 1
    assert summary["eventTypes"] == ["helmet_missing"]
    assert summary["overallConfidence"] == 0.7
    assert len(summary["keyEvents"]) == 1
