from src.ui_format import (
    current_media_text,
    format_confidence_percent,
    format_evidence_values,
    media_status_for_display,
)


def test_format_evidence_values_is_human_readable():
    text = format_evidence_values({"seatbelt_torso_iou": 0.123456, "seatbelt_count": 0})

    assert "seatbelt torso iou: 0.1235" in text
    assert "seatbelt count: 0" in text


def test_format_confidence_percent_handles_common_values():
    assert format_confidence_percent(0.0) == "0%"
    assert format_confidence_percent(0.875) == "87.5%"
    assert format_confidence_percent(1) == "100%"
    assert format_confidence_percent(None) == "N/A"


def test_media_status_for_display_follows_parent_processing_status():
    item = {"filename": "video.mp4", "status": "queued"}

    assert media_status_for_display(item, "processing") == "processing"
    assert media_status_for_display(item, "completed") == "completed"
    assert media_status_for_display({"status": "failed"}, "processing") == "failed"


def test_current_media_text_for_single_and_batch_jobs():
    single = {
        "status": "processing",
        "media": [{"filename": "video.mp4"}],
    }
    batch = {
        "status": "processing",
        "media": [{"filename": "a.mp4"}, {"filename": "b.mp4"}],
    }

    assert current_media_text(single) == "video.mp4"
    assert current_media_text(batch) == "Processing batch of 2 media files"
