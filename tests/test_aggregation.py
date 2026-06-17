from src.aggregation import aggregate_video_findings


def _frame(ts, name="seatbelt_missing", confidence=0.9):
    return {
        "frame_id": f"frame_{ts}",
        "frame_path": f"/tmp/frame_{ts}.jpg",
        "timestamp": float(ts),
        "video_id": "video_a",
        "vehicle_id": "Vehicle_A",
        "violations": [
            {
                "name": name,
                "description": f"{name} detected",
                "confidence": confidence,
            }
        ],
    }


def test_single_frame_violation_is_review_needed():
    summary = aggregate_video_findings(
        [_frame(20, name="phone_use")],
        video_id="video_a",
        vehicle_id="Vehicle_A",
    )

    assert summary["overall_status"] == "review_needed"
    assert summary["violations"][0]["status"] == "review_needed"


def test_sustained_seatbelt_after_grace_is_likely():
    summary = aggregate_video_findings(
        [_frame(16), _frame(18), _frame(20)],
        video_id="video_a",
        vehicle_id="Vehicle_A",
        seatbelt_grace_seconds=15,
    )

    assert summary["overall_status"] == "violation_likely"
    assert summary["violations"][0]["evidence_frame_count"] == 3


def test_seatbelt_only_during_grace_is_ignored():
    summary = aggregate_video_findings(
        [_frame(1), _frame(5), _frame(10)],
        video_id="video_a",
        vehicle_id="Vehicle_A",
        seatbelt_grace_seconds=15,
    )

    assert summary["overall_status"] == "clear"
    assert summary["violations"] == []


def test_nearby_findings_merge_into_one_event():
    summary = aggregate_video_findings(
        [
            _frame(20, name="phone_use"),
            _frame(22, name="phone_use"),
            _frame(24, name="phone_use"),
        ],
        video_id="video_a",
        merge_gap_seconds=5,
    )

    assert len(summary["violations"]) == 1
    assert summary["violations"][0]["start_time"] == 20.0
    assert summary["violations"][0]["end_time"] == 24.0
