from src.api.batches import BatchStore
from src.api.jobs import AnalysisSettings, JobStore
import src.chat_service as chat_service


def make_settings():
    return AnalysisSettings(fps=1.0, top_k=5, enable_vlm=False, device="cpu")


def make_completed_job(tmp_path):
    job_store = JobStore(tmp_path / "jobs")
    batch_store = BatchStore(tmp_path / "batches")
    record = job_store.create_job(
        filename="site-camera.mp4",
        content=b"video",
        query="worker without helmet or seatbelt",
        settings=make_settings(),
    )
    job_store.complete_job(record.job_id, sample_result(record.job_id))
    return job_store, batch_store, record


def sample_result(job_id: str):
    return {
        "jobId": job_id,
        "status": "completed",
        "media": {"id": "media", "name": "site-camera.mp4", "type": "video", "sizeBytes": 5},
        "query": "worker without helmet or seatbelt",
        "summary": {
            "framesAnalyzed": 5,
            "framesWithViolations": 4,
            "uniqueViolationTypes": 2,
            "summaryText": "Missing helmet and seatbelt findings need review.",
            "potentialEventCount": 6,
            "overallConfidence": 0.92,
        },
        "events": [
            {
                "id": "helmet-1",
                "type": "missing_helmet",
                "name": "Missing Helmet",
                "severity": "High",
                "description": "Worker without helmet.",
                "startTimestamp": "00:00:16",
                "endTimestamp": "00:00:46",
                "representativeConfidence": 0.96,
                "confidenceMin": 0.88,
                "confidenceMax": 0.96,
                "supportingFrameCount": 2,
                "supportingFrames": [
                    {"frameId": "frame-1", "frameNumber": 1, "timestamp": "00:00:46", "confidence": 0.96},
                    {"frameId": "frame-2", "frameNumber": 2, "timestamp": "00:00:16", "confidence": 0.88},
                ],
            },
            {
                "id": "helmet-2",
                "type": "missing_helmet",
                "name": "Missing Helmet",
                "severity": "High",
                "description": "Worker without helmet.",
                "startTimestamp": "00:00:19",
                "endTimestamp": "00:00:33",
                "representativeConfidence": 0.91,
                "confidenceMin": 0.87,
                "confidenceMax": 0.91,
                "supportingFrameCount": 2,
                "supportingFrames": [
                    {"frameId": "frame-3", "frameNumber": 3, "timestamp": "00:00:19", "confidence": 0.91},
                    {"frameId": "frame-5", "frameNumber": 5, "timestamp": "00:00:33", "confidence": 0.87},
                ],
            },
            {
                "id": "seatbelt-1",
                "type": "missing_seatbelt",
                "name": "Missing Seatbelt",
                "severity": "Medium",
                "description": "Driver without seatbelt.",
                "startTimestamp": "00:00:16",
                "endTimestamp": "00:00:46",
                "representativeConfidence": 0.86,
                "confidenceMin": 0.8,
                "confidenceMax": 0.86,
                "supportingFrameCount": 4,
                "supportingFrames": [
                    {"frameId": "frame-1", "frameNumber": 1, "timestamp": "00:00:46", "confidence": 0.86},
                    {"frameId": "frame-2", "frameNumber": 2, "timestamp": "00:00:16", "confidence": 0.8},
                    {"frameId": "frame-3", "frameNumber": 3, "timestamp": "00:00:19", "confidence": 0.84},
                    {"frameId": "frame-5", "frameNumber": 5, "timestamp": "00:00:33", "confidence": 0.82},
                ],
            },
        ],
        "violations": [],
        "frames": [],
        "technicalDetails": {"jobMetrics": {"duration": 12.3}, "debug": {"raw": "not sent"}},
    }


def ask(message: str, tmp_path, monkeypatch, *, include_job=True):
    monkeypatch.setattr(chat_service.SETTINGS, "chat_enabled", True)
    monkeypatch.setattr(chat_service.SETTINGS, "chat_provider", "mock")
    job_store, batch_store, record = make_completed_job(tmp_path)
    response = chat_service.answer_chat(
        message=message,
        job_store=job_store,
        batch_store=batch_store,
        job_id=record.job_id if include_job else None,
        include_current_result=True,
    )
    return response["answer"]


def normalized_blocks(text: str):
    return [block.strip().lower() for block in text.split("\n\n") if block.strip()]


def assert_no_repeated_blocks(text: str):
    blocks = normalized_blocks(text)
    assert len(blocks) == len(set(blocks))


def test_explain_result_template_is_concise_and_bulleted(monkeypatch, tmp_path):
    answer = ask("Explain this result.", tmp_path, monkeypatch)

    assert "This result found 2 violation types" in answer
    assert "- Missing Helmet:" in answer
    assert "- Missing Seatbelt:" in answer
    assert "Next:" in answer
    assert "technical JSON" not in answer
    assert len(answer.split()) < 120
    assert_no_repeated_blocks(answer)


def test_supporting_frames_template_lists_frames_once(monkeypatch, tmp_path):
    answer = ask("Which frames support the top finding?", tmp_path, monkeypatch)

    assert "The top finding is Missing Helmet." in answer
    assert "Supporting frames:" in answer
    assert answer.count("Frame 1 at 00:00:46") == 1
    assert answer.count("Frame 2 at 00:00:16") == 1
    assert answer.count("Supporting frames:") == 1
    assert "technical JSON" not in answer
    assert_no_repeated_blocks(answer)


def test_seatbelt_question_returns_grounded_missing_seatbelt_answer(monkeypatch, tmp_path):
    answer = ask("Was the driver wearing a seatbelt?", tmp_path, monkeypatch)

    assert "Video: site-camera.mp4" in answer
    assert "Job: job_" in answer
    assert "SafeTrace flagged Missing Seatbelt." in answer
    assert "- Severity: Medium" in answer
    assert "- Confidence: 86%" in answer
    assert "Frame 1 at 00:00:46" in answer
    assert "Frame 5 at 00:00:33" in answer
    assert "seatbelt may not be visible" in answer
    assert "manual confirmation" in answer


def test_helmet_question_returns_grounded_missing_helmet_answer(monkeypatch, tmp_path):
    answer = ask("Was anyone missing a helmet?", tmp_path, monkeypatch)

    assert "SafeTrace flagged Missing Helmet." in answer
    assert "- Severity: High" in answer
    assert "Frame 1 at 00:00:46" in answer
    assert "Frame 2 at 00:00:16" in answer
    assert "helmet may not be visible" in answer


def test_phone_question_without_phone_finding_does_not_hallucinate(monkeypatch, tmp_path):
    answer = ask("Is the driver using a phone while driving?", tmp_path, monkeypatch)

    assert "SafeTrace did not detect a phone-use violation in this result." in answer
    assert "did not detect" in answer
    assert "may not reliably support phone-use detection" in answer
    assert "SafeTrace flagged Phone" not in answer


def test_timestamp_and_confidence_questions_use_selected_result(monkeypatch, tmp_path):
    timestamp_answer = ask("What timestamp did the violation occur?", tmp_path, monkeypatch)
    confidence_answer = ask("What is the confidence?", tmp_path, monkeypatch)

    assert "Frame 1 at 00:00:46" in timestamp_answer
    assert "Frame 2 at 00:00:16" in timestamp_answer
    assert "Overall confidence for this result is 92%." in confidence_answer
    assert "Top finding: Missing Helmet" in confidence_answer


def test_no_selected_result_gives_selection_instruction(monkeypatch, tmp_path):
    answer = ask("Was the driver wearing a seatbelt?", tmp_path, monkeypatch, include_job=False)

    assert "I do not have a selected completed SafeTrace result" in answer
    assert "pass its job_id to /api/chat" in answer
    assert "select a completed result" in answer.lower()


def test_safe_or_unsafe_question_uses_detected_findings(monkeypatch, tmp_path):
    answer = ask("Was this video safe or unsafe?", tmp_path, monkeypatch)

    assert "unsafe or requiring review" in answer
    assert "Missing Helmet" in answer
    assert "Missing Seatbelt" in answer
    assert "automated review aid" in answer


def test_zip_upload_answer_prioritizes_frontend_before_api(monkeypatch, tmp_path):
    answer = ask("How do I upload a ZIP batch?", tmp_path, monkeypatch, include_job=False)

    assert "To upload a ZIP batch in the frontend:" in answer
    assert answer.index("1. Use the upload panel") < answer.index("POST /api/batches/analyze")
    assert answer.count("POST /api/batches/analyze") == 1
    assert_no_repeated_blocks(answer)


def test_confidence_answer_is_general_and_readable(monkeypatch, tmp_path):
    answer = ask("What does overall confidence mean?", tmp_path, monkeypatch)

    assert "not certainty" in answer
    assert "- model detections" in answer
    assert "confirm the evidence frames manually" in answer
    assert "technical JSON" not in answer
    assert len(answer.split()) < 90


def test_out_of_scope_question_is_refused(monkeypatch, tmp_path):
    answer = ask("What is the weather today?", tmp_path, monkeypatch)

    assert "I can only answer questions about SafeTrace" in answer


def test_batch_implementation_answer_is_developer_scoped(monkeypatch, tmp_path):
    answer = ask("Where is batch upload implemented?", tmp_path, monkeypatch)

    assert "src/api/batches.py" in answer
    assert "POST /api/batches/analyze" in answer
    assert "frontend-react/src/App.tsx" in answer
    assert_no_repeated_blocks(answer)


def test_assistant_unavailable_answer_is_actionable(monkeypatch, tmp_path):
    answer = ask("Why is the assistant unavailable?", tmp_path, monkeypatch)

    assert "SafeTrace analysis still works" in answer
    assert "SAFETRACE_CHAT_ENABLED=auto" in answer
    assert "llama-cpp-python" in answer
    assert "Next:" in answer


def test_prompt_contains_answer_quality_rules_and_vlm_distinction():
    context = chat_service.ChatContext(text=chat_service.SAFETRACE_HELP_TEXT, sources=["docs"])
    prompt = chat_service._build_prompt(message="Explain this result.", context=context)

    assert "Do not repeat the same point" in prompt
    assert "Keep most answers under 120 words" in prompt
    assert "explain frontend steps first" in prompt
    assert "The VLM explanation describes detected evidence" in prompt


def test_postprocess_removes_repetition_and_splits_dense_text(monkeypatch):
    monkeypatch.setattr(chat_service.SETTINGS, "chat_max_tokens", 200)
    repeated = (
        "SafeTrace found a missing helmet. SafeTrace found a missing helmet. "
        "Review the evidence frames. Review the evidence frames. "
        "Confirm the annotated regions manually. Confirm the annotated regions manually. "
        "Use the result as a review signal."
        "\n\n"
        "Review the evidence frames."
        "\n\n"
        "Review the evidence frames."
    )

    cleaned = chat_service._postprocess_answer(repeated)

    assert cleaned.count("SafeTrace found a missing helmet.") == 1
    assert cleaned.count("Review the evidence frames.") == 1
    assert len(cleaned) <= 1000
