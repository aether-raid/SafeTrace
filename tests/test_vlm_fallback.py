import subprocess

import httpx
import numpy as np
from pathlib import Path

import src.vlm_reasoner as vlm_reasoner
from src.safe_frame_ranking import parse_query_intent, score_frame_for_safe_mode, select_ranked_frames
from src.schemas import Detection, Violation
from src.vlm_reasoner import VLM_PROMPT, VlmReasoner, is_local_vlm_base_url, is_useful_vlm_output, sanitize_vlm_output


class FakeGenerateResponse:
    def __init__(self, payload):
        self._payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self._payload


class FakeProcessorBatch(dict):
    def to(self, device):
        self["device"] = device
        return self


class FakeChatTemplateProcessor:
    def __init__(self, decoded_text="Visible helmet evidence is uncertain due to glare."):
        self.decoded_text = decoded_text
        self.messages = None
        self.template_kwargs = None
        self.call_kwargs = None
        self.decode_output_ids = None
        self.decode_kwargs = None

    def apply_chat_template(self, messages, **kwargs):
        self.messages = messages
        self.template_kwargs = kwargs
        return "USER: <image>\nDescribe visible SafeTrace evidence.\nASSISTANT:"

    def __call__(self, **kwargs):
        self.call_kwargs = kwargs
        return FakeProcessorBatch({"input_ids": [1, 2, 3]})

    def batch_decode(self, output_ids, **kwargs):
        self.decode_output_ids = output_ids
        self.decode_kwargs = kwargs
        return [self.decoded_text]


class FakeNoTemplateProcessor(FakeChatTemplateProcessor):
    apply_chat_template = None


class FakeLocalModel:
    def __init__(self, fail=False):
        self.fail = fail
        self.generate_kwargs = None

    def generate(self, **kwargs):
        self.generate_kwargs = kwargs
        if self.fail:
            raise RuntimeError("image token mismatch")
        return [[1, 2, 3, 4]]


def make_local_reasoner(processor, model):
    reasoner = VlmReasoner.__new__(VlmReasoner)
    reasoner.device = "cpu"
    reasoner.provider = "local"
    reasoner.enabled = True
    reasoner._loaded = True
    reasoner._processor = processor
    reasoner._model = model
    reasoner.last_explanation_source = "rule_based"
    return reasoner


def make_violation():
    return Violation(
        name="helmet_missing",
        description="Worker head detected without overlapping helmet.",
        severity="high",
        confidence=0.9,
    )


def make_detection(label, bbox=(10, 10, 90, 90), confidence=0.9):
    mask = np.zeros((100, 100), dtype=bool)
    x1, y1, x2, y2 = [int(value) for value in bbox]
    mask[y1:y2, x1:x2] = True
    return Detection(
        label=label,
        raw_label=label,
        confidence=confidence,
        bbox=[float(value) for value in bbox],
        coarse_mask=mask,
    )


def output_path_from_worker_command(command):
    return Path(command[command.index("--output-json") + 1])


def input_path_from_worker_command(command):
    return Path(command[command.index("--input-json") + 1])


def test_vlm_rejects_non_local_base_url():
    assert is_local_vlm_base_url("http://127.0.0.1:11434") is True
    assert is_local_vlm_base_url("http://localhost:11434") is True
    assert is_local_vlm_base_url("https://example.com") is False


def test_disabled_vlm_returns_rule_based_fallback(monkeypatch):
    monkeypatch.setattr(vlm_reasoner.SETTINGS, "vlm_enabled", "disabled")
    monkeypatch.setattr(vlm_reasoner.SETTINGS, "enable_vlm", True)

    reasoner = VlmReasoner(device="cpu", enabled=True)
    text = reasoner.explain_violation(np.zeros((4, 4, 3), dtype=np.uint8), [make_violation()])

    assert reasoner.last_explanation_source == "rule_based"
    assert "Rule-based explanation" in text
    assert "helmet_missing" in text


def test_pipeline_rule_based_mode_does_not_construct_vlm_reasoner(monkeypatch):
    import src.pipeline as pipeline_module

    class FakeIndex:
        def __init__(self, embedder):  # noqa: ARG002
            pass

    def fail_if_vlm_constructed(*args, **kwargs):  # noqa: ARG001
        raise AssertionError("Rule-based analysis should not construct VlmReasoner")

    monkeypatch.setattr(pipeline_module.SETTINGS, "enable_vlm", False)
    monkeypatch.setattr(pipeline_module.SETTINGS, "vlm_enabled", "auto")
    monkeypatch.setattr(pipeline_module, "ClipEmbedder", lambda: object())
    monkeypatch.setattr(pipeline_module, "FaissIndex", FakeIndex)
    monkeypatch.setattr(pipeline_module, "YoloDetector", lambda: object())
    monkeypatch.setattr(pipeline_module, "MobileSamSegmenter", lambda: object())
    monkeypatch.setattr(pipeline_module, "VlmReasoner", fail_if_vlm_constructed)

    pipeline = pipeline_module.SafeTracePipeline()

    assert pipeline.vlm.provider == "rule_based"


def test_pipeline_fast_mode_does_not_construct_mobile_sam_by_default(monkeypatch):
    import src.pipeline as pipeline_module

    class FakeIndex:
        def __init__(self, embedder):  # noqa: ARG002
            pass

    def fail_if_mobile_sam_constructed(*args, **kwargs):  # noqa: ARG001
        raise AssertionError("Fast rule-based analysis should not construct MobileSAM")

    monkeypatch.setattr(pipeline_module.SETTINGS, "enable_vlm", False)
    monkeypatch.setattr(pipeline_module.SETTINGS, "vlm_enabled", "auto")
    monkeypatch.setattr(pipeline_module.SETTINGS, "mobile_sam_enabled", "disabled")
    monkeypatch.setattr(pipeline_module, "ClipEmbedder", lambda: object())
    monkeypatch.setattr(pipeline_module, "FaissIndex", FakeIndex)
    monkeypatch.setattr(pipeline_module, "YoloDetector", lambda: object())
    monkeypatch.setattr(pipeline_module, "MobileSamSegmenter", fail_if_mobile_sam_constructed)

    pipeline = pipeline_module.SafeTracePipeline()

    assert pipeline.segmenter.available is False


def test_pipeline_safe_mode_skips_embeddings_vlm_and_mobile_sam(monkeypatch):
    import src.pipeline as pipeline_module

    def fail_if_called(component):
        def inner(*args, **kwargs):  # noqa: ARG001
            raise AssertionError(f"safe mode should not construct {component}")
        return inner

    class FakeDetector:
        checkpoint = "checkpoints/yolov8s-seg.pt"

        def detect(self, image):  # noqa: ARG002
            return []

    monkeypatch.setattr(pipeline_module.SETTINGS, "analysis_safe_mode", True)
    monkeypatch.setattr(pipeline_module.SETTINGS, "safe_mode_allow_mobilesam", False)
    monkeypatch.setattr(pipeline_module.SETTINGS, "enable_vlm", True)
    monkeypatch.setattr(pipeline_module.SETTINGS, "vlm_profile", "lightweight_256m")
    monkeypatch.setattr(pipeline_module.SETTINGS, "mobile_sam_enabled", "auto")
    monkeypatch.setattr(pipeline_module.SETTINGS, "mobile_sam_worker_enabled", False)
    monkeypatch.setattr(pipeline_module, "ClipEmbedder", fail_if_called("ClipEmbedder"))
    monkeypatch.setattr(pipeline_module, "FaissIndex", fail_if_called("FaissIndex"))
    monkeypatch.setattr(pipeline_module, "MobileSamSegmenter", fail_if_called("MobileSamSegmenter"))
    monkeypatch.setattr(pipeline_module, "VlmReasoner", fail_if_called("VlmReasoner"))
    monkeypatch.setattr(pipeline_module, "YoloDetector", FakeDetector)

    pipeline = pipeline_module.SafeTracePipeline()

    assert pipeline.safe_mode is True
    assert pipeline.embedder is None
    assert pipeline.index is None
    assert pipeline.segmenter.available is False
    assert pipeline.vlm.provider == "rule_based"
    assert pipeline.component_diagnostics["embeddingRequested"] is False
    assert pipeline.component_diagnostics["vlmLoaded"] is False
    assert pipeline.component_diagnostics["mobileSamLoaded"] is False


def test_pipeline_safe_mode_allows_mobile_sam_after_frame_selection(monkeypatch, tmp_path):
    import src.pipeline as pipeline_module

    constructed = {"mobile_sam": 0, "refined": 0}

    class FakeDetector:
        checkpoint = "checkpoints/yolov8s-seg.pt"

        def detect(self, image):  # noqa: ARG002
            return [Detection(label="person", raw_label="person", confidence=0.9, bbox=[0, 0, 10, 10])]

    class FakeMobileSam:
        available = True

        def __init__(self, *args, **kwargs):  # noqa: ARG002
            constructed["mobile_sam"] += 1

        def refine(self, image, detections):  # noqa: ARG002
            constructed["refined"] += 1
            return detections

    frames = [tmp_path / f"frame_{index:06d}.jpg" for index in range(3)]
    for frame in frames:
        frame.write_bytes(b"placeholder")

    monkeypatch.setattr(pipeline_module.SETTINGS, "analysis_safe_mode", True)
    monkeypatch.setattr(pipeline_module.SETTINGS, "safe_mode_allow_mobilesam", True)
    monkeypatch.setattr(pipeline_module.SETTINGS, "mobile_sam_enabled", "true")
    monkeypatch.setattr(pipeline_module.SETTINGS, "mobile_sam_worker_enabled", False)
    monkeypatch.setattr(pipeline_module.SETTINGS, "enable_vlm", False)
    monkeypatch.setattr(pipeline_module.SETTINGS, "top_k", 1)
    monkeypatch.setattr(pipeline_module.SETTINGS, "data_dir", tmp_path)
    monkeypatch.setattr(pipeline_module, "ClipEmbedder", lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("ClipEmbedder should not load")))
    monkeypatch.setattr(pipeline_module, "FaissIndex", lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("FaissIndex should not load")))
    monkeypatch.setattr(pipeline_module, "VlmReasoner", lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("VLM should not load")))
    monkeypatch.setattr(pipeline_module, "YoloDetector", FakeDetector)
    monkeypatch.setattr(pipeline_module, "MobileSamSegmenter", FakeMobileSam)
    monkeypatch.setattr(pipeline_module, "imread_rgb", lambda path: np.zeros((32, 32, 3), dtype=np.uint8))
    monkeypatch.setattr(pipeline_module, "imwrite_rgb", lambda path, image: None)  # noqa: ARG005
    monkeypatch.setattr(pipeline_module, "evaluate_rules", lambda detections: [make_violation()])
    monkeypatch.setattr(
        pipeline_module.SafeTracePipeline,
        "_collect_input_frames",
        lambda self, inputs, fps, max_frames, **kwargs: (frames, [], {"videos": 0, "images": len(frames)}),  # noqa: ARG005
    )

    pipeline = pipeline_module.SafeTracePipeline()

    assert constructed["mobile_sam"] == 0

    result = pipeline.run([frames[0]], query="driver without seatbelt", fps=1.0, k=1)

    assert result
    assert constructed["mobile_sam"] == 1
    assert constructed["refined"] == 1
    assert pipeline.component_diagnostics["safeMode"] is True
    assert pipeline.component_diagnostics["safeModeMobileSamAllowed"] is True
    assert pipeline.component_diagnostics["embeddingRequested"] is False
    assert pipeline.component_diagnostics["vlmLoaded"] is False
    assert pipeline.component_diagnostics["mobileSamAttempted"] is True
    assert pipeline.component_diagnostics["mobileSamLoaded"] is True
    assert pipeline.component_diagnostics["effectiveExplanationMode"] == "rule_based_with_mobilesam"


def test_pipeline_safe_mode_mobile_sam_failure_uses_detector_box_fallback(monkeypatch, tmp_path):
    import src.pipeline as pipeline_module

    class FakeDetector:
        checkpoint = "checkpoints/yolov8s-seg.pt"

        def detect(self, image):  # noqa: ARG002
            return [Detection(label="person", raw_label="person", confidence=0.9, bbox=[0, 0, 10, 10])]

    class FailingMobileSam:
        available = True

        def __init__(self, *args, **kwargs):  # noqa: ARG002
            pass

        def refine(self, image, detections):  # noqa: ARG002
            raise RuntimeError("refine timeout")

    frame = tmp_path / "frame.jpg"
    frame.write_bytes(b"placeholder")

    monkeypatch.setattr(pipeline_module.SETTINGS, "analysis_safe_mode", True)
    monkeypatch.setattr(pipeline_module.SETTINGS, "safe_mode_allow_mobilesam", True)
    monkeypatch.setattr(pipeline_module.SETTINGS, "mobile_sam_enabled", "true")
    monkeypatch.setattr(pipeline_module.SETTINGS, "mobile_sam_worker_enabled", False)
    monkeypatch.setattr(pipeline_module.SETTINGS, "enable_vlm", False)
    monkeypatch.setattr(pipeline_module.SETTINGS, "data_dir", tmp_path)
    monkeypatch.setattr(pipeline_module, "ClipEmbedder", lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("ClipEmbedder should not load")))
    monkeypatch.setattr(pipeline_module, "FaissIndex", lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("FaissIndex should not load")))
    monkeypatch.setattr(pipeline_module, "VlmReasoner", lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("VLM should not load")))
    monkeypatch.setattr(pipeline_module, "YoloDetector", FakeDetector)
    monkeypatch.setattr(pipeline_module, "MobileSamSegmenter", FailingMobileSam)
    monkeypatch.setattr(pipeline_module, "imread_rgb", lambda path: np.zeros((32, 32, 3), dtype=np.uint8))
    monkeypatch.setattr(pipeline_module, "imwrite_rgb", lambda path, image: None)  # noqa: ARG005
    monkeypatch.setattr(pipeline_module, "evaluate_rules", lambda detections: [make_violation()])
    monkeypatch.setattr(
        pipeline_module.SafeTracePipeline,
        "_collect_input_frames",
        lambda self, inputs, fps, max_frames, **kwargs: ([frame], [], {"videos": 0, "images": 1}),  # noqa: ARG005
    )

    pipeline = pipeline_module.SafeTracePipeline()
    result = pipeline.run([frame], query="driver without seatbelt", fps=1.0, k=1)

    assert result
    assert pipeline.component_diagnostics["mobileSamAttempted"] is True
    assert pipeline.component_diagnostics["mobileSamLoaded"] is False
    assert pipeline.component_diagnostics["mobileSamFallbackReason"] == "RuntimeError"


def test_mobile_sam_worker_disabled_does_not_launch_subprocess(monkeypatch, tmp_path):
    import src.mobile_sam_worker_client as client_module

    checkpoint = tmp_path / "mobile_sam.pt"
    checkpoint.write_bytes(b"checkpoint")

    def fail_if_run(*args, **kwargs):  # noqa: ARG001
        raise AssertionError("worker subprocess should not launch when disabled")

    monkeypatch.setattr(client_module.SETTINGS, "data_dir", tmp_path)
    monkeypatch.setattr(client_module.SETTINGS, "project_root", tmp_path)
    monkeypatch.setattr(client_module.SETTINGS, "mobile_sam_enabled", "true")
    monkeypatch.setattr(client_module.SETTINGS, "mobile_sam_worker_enabled", False)
    monkeypatch.setattr(client_module.subprocess, "run", fail_if_run)

    detection = make_detection("person")
    segmenter = client_module.MobileSamWorkerSegmenter(checkpoint=checkpoint)
    refined = segmenter.refine(tmp_path / "frame.jpg", [detection])

    assert refined[0].refined_mask is not None
    assert segmenter.last_diagnostics["mobileSamWorkerAttempted"] is False
    assert segmenter.last_diagnostics["mobileSamRefinementSource"] == "disabled"


def test_mobile_sam_worker_success_result_is_consumed(monkeypatch, tmp_path):
    import src.mobile_sam_worker_client as client_module
    from src.mask_encoding import encode_bool_mask

    checkpoint = tmp_path / "mobile_sam.pt"
    checkpoint.write_bytes(b"checkpoint")
    mask = np.zeros((100, 100), dtype=bool)
    mask[5:20, 5:20] = True

    def fake_run(command, **kwargs):  # noqa: ARG001
        output_path = output_path_from_worker_command(command)
        output_path.write_text(
            client_module.json.dumps(
                {"ok": True, "detections": [{"index": 0, "hasRefinedMask": True, "refinedMask": encode_bool_mask(mask)}]}
            ),
            encoding="utf-8",
        )
        return subprocess.CompletedProcess(command, 0, "", "")

    monkeypatch.setattr(client_module.SETTINGS, "data_dir", tmp_path)
    monkeypatch.setattr(client_module.SETTINGS, "project_root", tmp_path)
    monkeypatch.setattr(client_module.SETTINGS, "mobile_sam_enabled", "true")
    monkeypatch.setattr(client_module.SETTINGS, "mobile_sam_worker_enabled", True)
    monkeypatch.setattr(client_module.SETTINGS, "mobile_sam_worker_timeout_seconds", 7)
    monkeypatch.setattr(client_module.subprocess, "run", fake_run)

    detection = make_detection("person")
    segmenter = client_module.MobileSamWorkerSegmenter(checkpoint=checkpoint)
    refined = segmenter.refine(tmp_path / "frame.jpg", [detection])

    assert bool(refined[0].refined_mask[6, 6]) is True
    assert segmenter.last_diagnostics["mobileSamWorkerAttempted"] is True
    assert segmenter.last_diagnostics["mobileSamWorkerSucceeded"] is True
    assert segmenter.last_diagnostics["mobileSamWorkerTimedOut"] is False
    assert segmenter.last_diagnostics["mobileSamRefinementSource"] == "worker"


def test_mobile_sam_worker_timeout_falls_back_without_failure(monkeypatch, tmp_path):
    import src.mobile_sam_worker_client as client_module

    checkpoint = tmp_path / "mobile_sam.pt"
    checkpoint.write_bytes(b"checkpoint")

    def timeout_run(command, **kwargs):  # noqa: ARG001
        raise subprocess.TimeoutExpired(command, 1.0)

    monkeypatch.setattr(client_module.SETTINGS, "data_dir", tmp_path)
    monkeypatch.setattr(client_module.SETTINGS, "project_root", tmp_path)
    monkeypatch.setattr(client_module.SETTINGS, "mobile_sam_enabled", "true")
    monkeypatch.setattr(client_module.SETTINGS, "mobile_sam_worker_enabled", True)
    monkeypatch.setattr(client_module.subprocess, "run", timeout_run)

    detection = make_detection("person")
    segmenter = client_module.MobileSamWorkerSegmenter(checkpoint=checkpoint)
    refined = segmenter.refine(tmp_path / "frame.jpg", [detection])

    assert refined[0].refined_mask is not None
    assert segmenter.last_diagnostics["mobileSamWorkerTimedOut"] is True
    assert segmenter.last_diagnostics["mobileSamFallbackReason"] == "worker_timeout"
    assert segmenter.last_diagnostics["mobileSamRefinementSource"] == "fallback"


def test_mobile_sam_worker_nonzero_exit_falls_back_without_failure(monkeypatch, tmp_path):
    import src.mobile_sam_worker_client as client_module

    checkpoint = tmp_path / "mobile_sam.pt"
    checkpoint.write_bytes(b"checkpoint")

    def nonzero_run(command, **kwargs):  # noqa: ARG001
        output_path = output_path_from_worker_command(command)
        output_path.write_text('{"ok": false, "errorType": "NativeCrash"}', encoding="utf-8")
        return subprocess.CompletedProcess(command, 9, "", "native crash")

    monkeypatch.setattr(client_module.SETTINGS, "data_dir", tmp_path)
    monkeypatch.setattr(client_module.SETTINGS, "project_root", tmp_path)
    monkeypatch.setattr(client_module.SETTINGS, "mobile_sam_enabled", "true")
    monkeypatch.setattr(client_module.SETTINGS, "mobile_sam_worker_enabled", True)
    monkeypatch.setattr(client_module.subprocess, "run", nonzero_run)

    detection = make_detection("person")
    segmenter = client_module.MobileSamWorkerSegmenter(checkpoint=checkpoint)
    refined = segmenter.refine(tmp_path / "frame.jpg", [detection])

    assert refined[0].refined_mask is not None
    assert segmenter.last_diagnostics["mobileSamWorkerExitCode"] == 9
    assert segmenter.last_diagnostics["mobileSamFallbackReason"] == "NativeCrash"
    assert segmenter.last_diagnostics["mobileSamRefinementSource"] == "fallback"


def test_mobile_sam_worker_invalid_json_falls_back_without_failure(monkeypatch, tmp_path):
    import src.mobile_sam_worker_client as client_module

    checkpoint = tmp_path / "mobile_sam.pt"
    checkpoint.write_bytes(b"checkpoint")

    def invalid_json_run(command, **kwargs):  # noqa: ARG001
        output_path = output_path_from_worker_command(command)
        output_path.write_text("not-json", encoding="utf-8")
        return subprocess.CompletedProcess(command, 0, "", "")

    monkeypatch.setattr(client_module.SETTINGS, "data_dir", tmp_path)
    monkeypatch.setattr(client_module.SETTINGS, "project_root", tmp_path)
    monkeypatch.setattr(client_module.SETTINGS, "mobile_sam_enabled", "true")
    monkeypatch.setattr(client_module.SETTINGS, "mobile_sam_worker_enabled", True)
    monkeypatch.setattr(client_module.subprocess, "run", invalid_json_run)

    detection = make_detection("person")
    segmenter = client_module.MobileSamWorkerSegmenter(checkpoint=checkpoint)
    refined = segmenter.refine(tmp_path / "frame.jpg", [detection])

    assert refined[0].refined_mask is not None
    assert segmenter.last_diagnostics["mobileSamWorkerExitCode"] == 0
    assert "invalid_worker_json" in segmenter.last_diagnostics["mobileSamFallbackReason"]
    assert segmenter.last_diagnostics["mobileSamRefinementSource"] == "fallback"


def test_lightweight_vlm_worker_disabled_does_not_launch_subprocess(monkeypatch, tmp_path):
    import src.lightweight_vlm_worker_client as client_module

    model_dir = tmp_path / "models" / "vlm" / "lightweight-256m"
    model_dir.mkdir(parents=True)

    def fail_if_run(*args, **kwargs):  # noqa: ARG001
        raise AssertionError("worker subprocess should not launch when disabled")

    monkeypatch.setattr(client_module.SETTINGS, "data_dir", tmp_path)
    monkeypatch.setattr(client_module.SETTINGS, "project_root", tmp_path)
    monkeypatch.setattr(client_module.SETTINGS, "vlm_enabled", "true")
    monkeypatch.setattr(client_module.SETTINGS, "lightweight_vlm_worker_enabled", False)
    monkeypatch.setattr(client_module.subprocess, "run", fail_if_run)

    reasoner = client_module.LightweightVlmWorkerReasoner(model_dir=model_dir)
    text = reasoner.explain_violation(np.zeros((16, 16, 3), dtype=np.uint8), [make_violation()])

    assert "Rule-based explanation" in text
    assert reasoner.last_diagnostics["lightweightVlmWorkerAttempted"] is False
    assert reasoner.last_diagnostics["lightweightVlmExplanationSource"] == "disabled"


def test_lightweight_vlm_worker_success_result_is_consumed(monkeypatch, tmp_path):
    import src.lightweight_vlm_worker_client as client_module

    model_dir = tmp_path / "models" / "vlm" / "lightweight-256m"
    model_dir.mkdir(parents=True)

    def fake_run(command, **kwargs):  # noqa: ARG001
        request = client_module.json.loads(input_path_from_worker_command(command).read_text(encoding="utf-8"))
        assert request["profile"] == "lightweight_256m"
        assert request["maxTokens"] <= 96
        assert request["generationTimeoutSeconds"] >= 10.0
        output_path = output_path_from_worker_command(command)
        output_path.write_text(
            client_module.json.dumps(
                {
                    "ok": True,
                    "explanation": "Visible safety evidence shows the worker area and helmet finding for review.",
                    "explanationSource": "vlm_lightweight",
                    "modelProfile": "lightweight_256m",
                    "generationTimeoutSeconds": request["generationTimeoutSeconds"],
                    "maxTokens": request["maxTokens"],
                }
            ),
            encoding="utf-8",
        )
        return subprocess.CompletedProcess(command, 0, "", "")

    monkeypatch.setattr(client_module.SETTINGS, "data_dir", tmp_path)
    monkeypatch.setattr(client_module.SETTINGS, "project_root", tmp_path)
    monkeypatch.setattr(client_module.SETTINGS, "vlm_enabled", "true")
    monkeypatch.setattr(client_module.SETTINGS, "lightweight_vlm_worker_enabled", True)
    monkeypatch.setattr(client_module.SETTINGS, "lightweight_vlm_worker_timeout_seconds", 7)
    monkeypatch.setattr(client_module.subprocess, "run", fake_run)

    reasoner = client_module.LightweightVlmWorkerReasoner(model_dir=model_dir)
    text = reasoner.explain_violation(np.zeros((16, 16, 3), dtype=np.uint8), [make_violation()])

    assert "Visible safety evidence" in text
    assert reasoner.last_explanation_source == "vlm_lightweight"
    assert reasoner.last_diagnostics["lightweightVlmWorkerAttempted"] is True
    assert reasoner.last_diagnostics["lightweightVlmWorkerSucceeded"] is True
    assert reasoner.last_diagnostics["lightweightVlmExplanationSource"] == "vlm_lightweight"
    assert reasoner.last_diagnostics["lightweightVlmMaxTokens"] <= 96


def test_lightweight_vlm_worker_timeout_falls_back_without_failure(monkeypatch, tmp_path):
    import src.lightweight_vlm_worker_client as client_module

    model_dir = tmp_path / "models" / "vlm" / "lightweight-256m"
    model_dir.mkdir(parents=True)

    def timeout_run(command, **kwargs):  # noqa: ARG001
        raise subprocess.TimeoutExpired(command, 1.0)

    monkeypatch.setattr(client_module.SETTINGS, "data_dir", tmp_path)
    monkeypatch.setattr(client_module.SETTINGS, "project_root", tmp_path)
    monkeypatch.setattr(client_module.SETTINGS, "vlm_enabled", "true")
    monkeypatch.setattr(client_module.SETTINGS, "lightweight_vlm_worker_enabled", True)
    monkeypatch.setattr(client_module.subprocess, "run", timeout_run)

    reasoner = client_module.LightweightVlmWorkerReasoner(model_dir=model_dir)
    text = reasoner.explain_violation(np.zeros((16, 16, 3), dtype=np.uint8), [make_violation()])

    assert "Rule-based explanation" in text
    assert reasoner.last_diagnostics["lightweightVlmWorkerTimedOut"] is True
    assert reasoner.last_diagnostics["lightweightVlmFallbackReason"] == "worker_timeout"
    assert reasoner.last_diagnostics["lightweightVlmExplanationSource"] == "rule_based"


def test_lightweight_vlm_worker_nonzero_exit_falls_back_without_failure(monkeypatch, tmp_path):
    import src.lightweight_vlm_worker_client as client_module

    model_dir = tmp_path / "models" / "vlm" / "lightweight-256m"
    model_dir.mkdir(parents=True)

    def nonzero_run(command, **kwargs):  # noqa: ARG001
        output_path = output_path_from_worker_command(command)
        output_path.write_text('{"ok": false, "errorType": "NativeCrash"}', encoding="utf-8")
        return subprocess.CompletedProcess(command, 9, "", "native crash")

    monkeypatch.setattr(client_module.SETTINGS, "data_dir", tmp_path)
    monkeypatch.setattr(client_module.SETTINGS, "project_root", tmp_path)
    monkeypatch.setattr(client_module.SETTINGS, "vlm_enabled", "true")
    monkeypatch.setattr(client_module.SETTINGS, "lightweight_vlm_worker_enabled", True)
    monkeypatch.setattr(client_module.subprocess, "run", nonzero_run)

    reasoner = client_module.LightweightVlmWorkerReasoner(model_dir=model_dir)
    text = reasoner.explain_violation(np.zeros((16, 16, 3), dtype=np.uint8), [make_violation()])

    assert "Rule-based explanation" in text
    assert reasoner.last_diagnostics["lightweightVlmWorkerExitCode"] == 9
    assert reasoner.last_diagnostics["lightweightVlmFallbackReason"] == "NativeCrash"


def test_lightweight_vlm_worker_invalid_json_falls_back_without_failure(monkeypatch, tmp_path):
    import src.lightweight_vlm_worker_client as client_module

    model_dir = tmp_path / "models" / "vlm" / "lightweight-256m"
    model_dir.mkdir(parents=True)

    def invalid_json_run(command, **kwargs):  # noqa: ARG001
        output_path = output_path_from_worker_command(command)
        output_path.write_text("not-json", encoding="utf-8")
        return subprocess.CompletedProcess(command, 0, "", "")

    monkeypatch.setattr(client_module.SETTINGS, "data_dir", tmp_path)
    monkeypatch.setattr(client_module.SETTINGS, "project_root", tmp_path)
    monkeypatch.setattr(client_module.SETTINGS, "vlm_enabled", "true")
    monkeypatch.setattr(client_module.SETTINGS, "lightweight_vlm_worker_enabled", True)
    monkeypatch.setattr(client_module.subprocess, "run", invalid_json_run)

    reasoner = client_module.LightweightVlmWorkerReasoner(model_dir=model_dir)
    text = reasoner.explain_violation(np.zeros((16, 16, 3), dtype=np.uint8), [make_violation()])

    assert "Rule-based explanation" in text
    assert reasoner.last_diagnostics["lightweightVlmWorkerExitCode"] == 0
    assert "invalid_worker_json" in reasoner.last_diagnostics["lightweightVlmFallbackReason"]


def test_lightweight_vlm_worker_quality_rejection_records_reason(monkeypatch, tmp_path):
    import src.lightweight_vlm_worker_client as client_module

    model_dir = tmp_path / "models" / "vlm" / "lightweight-256m"
    model_dir.mkdir(parents=True)

    def rejected_run(command, **kwargs):  # noqa: ARG001
        output_path = output_path_from_worker_command(command)
        output_path.write_text(
            client_module.json.dumps(
                {
                    "ok": False,
                    "errorType": "VlmFallback",
                    "fallbackReason": "quality:too short",
                    "qualityIssue": "too short",
                    "rawTextPreview": "unclear",
                    "cleanTextPreview": "unclear",
                    "generationTimeoutSeconds": 50.0,
                    "maxTokens": 64,
                }
            ),
            encoding="utf-8",
        )
        return subprocess.CompletedProcess(command, 3, "", "")

    monkeypatch.setattr(client_module.SETTINGS, "data_dir", tmp_path)
    monkeypatch.setattr(client_module.SETTINGS, "project_root", tmp_path)
    monkeypatch.setattr(client_module.SETTINGS, "vlm_enabled", "true")
    monkeypatch.setattr(client_module.SETTINGS, "lightweight_vlm_worker_enabled", True)
    monkeypatch.setattr(client_module.subprocess, "run", rejected_run)

    reasoner = client_module.LightweightVlmWorkerReasoner(model_dir=model_dir)
    text = reasoner.explain_violation(np.zeros((16, 16, 3), dtype=np.uint8), [make_violation()])

    assert "Rule-based explanation" in text
    assert reasoner.last_diagnostics["lightweightVlmWorkerExitCode"] == 3
    assert reasoner.last_diagnostics["lightweightVlmFallbackReason"] == "quality:too short"
    assert reasoner.last_diagnostics["lightweightVlmQualityIssue"] == "too short"
    assert reasoner.last_diagnostics["lightweightVlmCleanTextPreview"] == "unclear"


def test_lightweight_profile_uses_simple_visual_prompt(monkeypatch):
    from src.vlm_reasoner import VLM_PROMPT, VlmReasoner

    monkeypatch.setattr("src.vlm_reasoner.SETTINGS.vlm_profile", "lightweight_256m")
    reasoner = VlmReasoner(enabled=False)

    prompt = reasoner._prompt_for(
        [Violation(name="seatbelt_missing", description="Missing seatbelt", severity="high", confidence=0.9)]
    )

    assert prompt == "Describe the visible safety evidence in this image in one short sentence."
    assert "seatbelt_missing" not in prompt
    assert prompt != VLM_PROMPT


def test_pipeline_safe_mode_uses_mobile_sam_worker_after_frame_selection(monkeypatch, tmp_path):
    import src.pipeline as pipeline_module

    constructed = {"worker": 0, "refined": 0}

    class FakeDetector:
        checkpoint = "checkpoints/yolov8s-seg.pt"

        def detect(self, image):  # noqa: ARG002
            return [make_detection("person")]

    class FakeWorker:
        available = True

        def __init__(self, *args, **kwargs):  # noqa: ARG002
            constructed["worker"] += 1
            self.last_diagnostics = {
                "mobileSamWorkerEnabled": True,
                "mobileSamWorkerTimeoutSeconds": 60,
                "mobileSamWorkerAttempted": False,
                "mobileSamWorkerSucceeded": False,
                "mobileSamWorkerTimedOut": False,
                "mobileSamWorkerExitCode": None,
                "mobileSamFallbackReason": None,
                "mobileSamRefinementSource": "disabled",
            }

        def refine(self, image, detections):  # noqa: ARG002
            constructed["refined"] += 1
            self.last_diagnostics = {
                "mobileSamWorkerEnabled": True,
                "mobileSamWorkerTimeoutSeconds": 60,
                "mobileSamWorkerAttempted": True,
                "mobileSamWorkerSucceeded": True,
                "mobileSamWorkerTimedOut": False,
                "mobileSamWorkerExitCode": 0,
                "mobileSamFallbackReason": None,
                "mobileSamRefinementSource": "worker",
            }
            detections[0].refined_mask = detections[0].coarse_mask
            return detections

    frame = tmp_path / "frame.jpg"
    frame.write_bytes(b"placeholder")

    monkeypatch.setattr(pipeline_module.SETTINGS, "analysis_safe_mode", True)
    monkeypatch.setattr(pipeline_module.SETTINGS, "safe_mode_allow_mobilesam", True)
    monkeypatch.setattr(pipeline_module.SETTINGS, "mobile_sam_enabled", "true")
    monkeypatch.setattr(pipeline_module.SETTINGS, "mobile_sam_worker_enabled", True)
    monkeypatch.setattr(pipeline_module.SETTINGS, "mobile_sam_worker_timeout_seconds", 60)
    monkeypatch.setattr(pipeline_module.SETTINGS, "enable_vlm", False)
    monkeypatch.setattr(pipeline_module.SETTINGS, "top_k", 1)
    monkeypatch.setattr(pipeline_module.SETTINGS, "data_dir", tmp_path)
    monkeypatch.setattr(pipeline_module, "ClipEmbedder", lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("ClipEmbedder should not load")))
    monkeypatch.setattr(pipeline_module, "FaissIndex", lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("FaissIndex should not load")))
    monkeypatch.setattr(pipeline_module, "VlmReasoner", lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("VLM should not load")))
    monkeypatch.setattr(pipeline_module, "MobileSamSegmenter", lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("direct MobileSAM should not load")))
    monkeypatch.setattr(pipeline_module, "MobileSamWorkerSegmenter", FakeWorker)
    monkeypatch.setattr(pipeline_module, "YoloDetector", FakeDetector)
    monkeypatch.setattr(pipeline_module, "imread_rgb", lambda path: np.zeros((100, 100, 3), dtype=np.uint8))
    monkeypatch.setattr(pipeline_module, "imwrite_rgb", lambda path, image: None)  # noqa: ARG005
    monkeypatch.setattr(pipeline_module, "evaluate_rules", lambda detections: [make_violation()])
    monkeypatch.setattr(
        pipeline_module.SafeTracePipeline,
        "_collect_input_frames",
        lambda self, inputs, fps, max_frames, **kwargs: ([frame], [], {"videos": 0, "images": 1}),  # noqa: ARG005
    )

    pipeline = pipeline_module.SafeTracePipeline()
    result = pipeline.run([frame], query="driver without seatbelt", fps=1.0, k=1)

    assert result
    assert constructed["worker"] == 1
    assert constructed["refined"] == 1
    assert pipeline.component_diagnostics["mobileSamWorkerEnabled"] is True
    assert pipeline.component_diagnostics["mobileSamWorkerAttempted"] is True
    assert pipeline.component_diagnostics["mobileSamWorkerSucceeded"] is True
    assert pipeline.component_diagnostics["mobileSamWorkerExitCode"] == 0
    assert pipeline.component_diagnostics["mobileSamLoaded"] is False
    assert pipeline.component_diagnostics["mobileSamRefinementSource"] == "worker"
    assert pipeline.component_diagnostics["embeddingRequested"] is False
    assert pipeline.component_diagnostics["vlmLoaded"] is False
    assert result[0]["search_metadata"]["mobileSamRefinement"]["mobileSamRefinementSource"] == "worker"


def test_pipeline_safe_mode_uses_lightweight_vlm_worker_after_frame_selection(monkeypatch, tmp_path):
    import src.pipeline as pipeline_module

    constructed = {"worker": 0, "explained": 0}

    class FakeDetector:
        checkpoint = "checkpoints/yolov8s-seg.pt"

        def detect(self, image):  # noqa: ARG002
            return [make_detection("person")]

    class FakeVlmWorker:
        provider = "vlm_lightweight_worker"
        enabled = True

        def __init__(self, *args, **kwargs):  # noqa: ARG002
            constructed["worker"] += 1
            self.last_explanation_source = "rule_based"
            self.last_diagnostics = {
                "lightweightVlmWorkerEnabled": True,
                "lightweightVlmWorkerTimeoutSeconds": 60,
                "lightweightVlmWorkerAttempted": False,
                "lightweightVlmWorkerSucceeded": False,
                "lightweightVlmWorkerTimedOut": False,
                "lightweightVlmWorkerExitCode": None,
                "lightweightVlmFallbackReason": None,
                "lightweightVlmExplanationSource": "rule_based",
            }

        def explain_violation(self, image, violations):  # noqa: ARG002
            constructed["explained"] += 1
            self.last_explanation_source = "vlm_lightweight"
            self.last_diagnostics = {
                "lightweightVlmWorkerEnabled": True,
                "lightweightVlmWorkerTimeoutSeconds": 60,
                "lightweightVlmWorkerAttempted": True,
                "lightweightVlmWorkerSucceeded": True,
                "lightweightVlmWorkerTimedOut": False,
                "lightweightVlmWorkerExitCode": 0,
                "lightweightVlmFallbackReason": None,
                "lightweightVlmExplanationSource": "vlm_lightweight",
            }
            return "Visible safety evidence supports the missing helmet finding for reviewer confirmation."

    frame = tmp_path / "frame.jpg"
    frame.write_bytes(b"placeholder")

    monkeypatch.setattr(pipeline_module.SETTINGS, "analysis_safe_mode", True)
    monkeypatch.setattr(pipeline_module.SETTINGS, "safe_mode_allow_mobilesam", False)
    monkeypatch.setattr(pipeline_module.SETTINGS, "mobile_sam_enabled", "disabled")
    monkeypatch.setattr(pipeline_module.SETTINGS, "mobile_sam_worker_enabled", False)
    monkeypatch.setattr(pipeline_module.SETTINGS, "enable_vlm", True)
    monkeypatch.setattr(pipeline_module.SETTINGS, "vlm_enabled", "true")
    monkeypatch.setattr(pipeline_module.SETTINGS, "vlm_profile", "lightweight_256m")
    monkeypatch.setattr(pipeline_module.SETTINGS, "lightweight_vlm_worker_enabled", True)
    monkeypatch.setattr(pipeline_module.SETTINGS, "lightweight_vlm_worker_timeout_seconds", 60)
    monkeypatch.setattr(pipeline_module.SETTINGS, "top_k", 1)
    monkeypatch.setattr(pipeline_module.SETTINGS, "data_dir", tmp_path)
    monkeypatch.setattr(pipeline_module, "ClipEmbedder", lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("ClipEmbedder should not load")))
    monkeypatch.setattr(pipeline_module, "FaissIndex", lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("FaissIndex should not load")))
    monkeypatch.setattr(pipeline_module, "VlmReasoner", lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("direct VLM should not load")))
    monkeypatch.setattr(pipeline_module, "MobileSamSegmenter", lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("MobileSAM should not load")))
    monkeypatch.setattr(pipeline_module, "LightweightVlmWorkerReasoner", FakeVlmWorker)
    monkeypatch.setattr(pipeline_module, "YoloDetector", FakeDetector)
    monkeypatch.setattr(pipeline_module, "imread_rgb", lambda path: np.zeros((100, 100, 3), dtype=np.uint8))
    monkeypatch.setattr(pipeline_module, "imwrite_rgb", lambda path, image: None)  # noqa: ARG005
    monkeypatch.setattr(pipeline_module, "evaluate_rules", lambda detections: [make_violation()])
    monkeypatch.setattr(
        pipeline_module.SafeTracePipeline,
        "_collect_input_frames",
        lambda self, inputs, fps, max_frames, **kwargs: ([frame], [], {"videos": 0, "images": 1}),  # noqa: ARG005
    )

    pipeline = pipeline_module.SafeTracePipeline()
    result = pipeline.run([frame], query="worker without helmet", fps=1.0, k=1)

    assert result
    assert constructed["worker"] == 1
    assert constructed["explained"] == 1
    assert pipeline.component_diagnostics["safeMode"] is True
    assert pipeline.component_diagnostics["embeddingRequested"] is False
    assert pipeline.component_diagnostics["vlmLoaded"] is False
    assert pipeline.component_diagnostics["lightweightVlmWorkerEnabled"] is True
    assert pipeline.component_diagnostics["lightweightVlmWorkerAttempted"] is True
    assert pipeline.component_diagnostics["lightweightVlmWorkerSucceeded"] is True
    assert pipeline.component_diagnostics["effectiveExplanationMode"] == "lightweight_256m"
    assert result[0]["explanation_source"] == "vlm_lightweight"
    assert result[0]["search_metadata"]["lightweightVlmExplanation"]["lightweightVlmWorkerSucceeded"] is True


def test_pipeline_safe_mode_direct_run_completes_without_embeddings(monkeypatch, tmp_path):
    import src.pipeline as pipeline_module

    class FakeDetector:
        checkpoint = "checkpoints/yolov8s-seg.pt"

        def detect(self, image):  # noqa: ARG002
            return []

    def fail_if_called(component):
        def inner(*args, **kwargs):  # noqa: ARG001
            raise AssertionError(f"safe mode should not construct {component}")
        return inner

    frame = tmp_path / "frame.jpg"
    frame.write_bytes(b"placeholder")
    monkeypatch.setattr(pipeline_module.SETTINGS, "analysis_safe_mode", True)
    monkeypatch.setattr(pipeline_module.SETTINGS, "enable_vlm", True)
    monkeypatch.setattr(pipeline_module.SETTINGS, "vlm_profile", "lightweight_256m")
    monkeypatch.setattr(pipeline_module.SETTINGS, "mobile_sam_worker_enabled", False)
    monkeypatch.setattr(pipeline_module.SETTINGS, "top_k", 1)
    monkeypatch.setattr(pipeline_module, "ClipEmbedder", fail_if_called("ClipEmbedder"))
    monkeypatch.setattr(pipeline_module, "FaissIndex", fail_if_called("FaissIndex"))
    monkeypatch.setattr(pipeline_module, "MobileSamSegmenter", fail_if_called("MobileSamSegmenter"))
    monkeypatch.setattr(pipeline_module, "VlmReasoner", fail_if_called("VlmReasoner"))
    monkeypatch.setattr(pipeline_module, "YoloDetector", FakeDetector)
    monkeypatch.setattr(pipeline_module, "imread_rgb", lambda path: np.zeros((4, 4, 3), dtype=np.uint8))
    monkeypatch.setattr(pipeline_module, "evaluate_rules", lambda detections: [make_violation()])

    pipeline = pipeline_module.SafeTracePipeline()
    monkeypatch.setattr(
        pipeline,
        "_collect_input_frames",
        lambda inputs, fps, max_frames, **kwargs: ([frame], [], {"videos": 0, "images": 1}),  # noqa: ARG005
    )

    result = pipeline.run([frame], query="worker without helmet", fps=1.0, k=1)

    assert len(result) == 1
    assert result[0]["violations"][0]["name"] == "helmet_missing"
    assert result[0]["explanation_source"] == "rule_based"
    assert result[0]["search_metadata"]["embeddingBypassed"] is True
    assert pipeline.component_diagnostics["embeddingRequested"] is False
    assert pipeline.component_diagnostics["vlmAttempted"] is False
    assert result[0]["search_metadata"]["mode"] == "safe_ranked_frame_scan"
    assert result[0]["search_metadata"]["queryIntent"]["intents"]


def test_safe_mode_query_intent_parsing_for_driving_and_ppe_queries():
    seatbelt = parse_query_intent("driver not wearing seatbelt")
    phone = parse_query_intent("using mobile phone while driving")
    helmet = parse_query_intent("worker without hard hat")
    damage = parse_query_intent("damaged equipment near machinery")

    assert "seatbelt" in seatbelt.intents
    assert "person" in seatbelt.intents
    assert "seatbelt" in seatbelt.relevant_labels
    assert "phone" in phone.intents
    assert "hand" in phone.relevant_labels
    assert "helmet" in helmet.intents
    assert "helmet" in helmet.relevant_labels
    assert "damage" in damage.intents
    assert "machinery" in damage.intents


def test_safe_mode_ranking_prefers_violation_and_person_frames_over_road_only():
    intent = parse_query_intent("driver without seatbelt")
    road = score_frame_for_safe_mode(
        frame_path=Path("road.jpg"),
        frame_index=0,
        total_frames=3,
        detections=[make_detection("car", bbox=(45, 35, 60, 48))],
        violations=[],
        query_intent=intent,
        image_shape=(100, 100, 3),
    )
    person = score_frame_for_safe_mode(
        frame_path=Path("driver.jpg"),
        frame_index=1,
        total_frames=3,
        detections=[make_detection("person"), make_detection("torso", bbox=(20, 30, 80, 80))],
        violations=[Violation(name="seatbelt_missing", description="Missing seatbelt.", confidence=0.95)],
        query_intent=intent,
        image_shape=(100, 100, 3),
    )

    assert person.raw_score > road.raw_score
    assert "violation candidate was found" in person.reasons
    assert "road-only or distant-vehicle frame deprioritized" in road.reasons


def test_safe_mode_selection_keeps_late_high_scoring_violation_frame():
    intent = parse_query_intent("driver without seatbelt")
    candidates = []
    for index in range(6):
        detections = [make_detection("car", bbox=(45, 40, 55, 48))]
        violations = []
        if index == 5:
            detections = [make_detection("person"), make_detection("torso", bbox=(20, 30, 80, 80))]
            violations = [Violation(name="seatbelt_missing", description="Missing seatbelt.", confidence=0.9)]
        candidates.append(
            score_frame_for_safe_mode(
                frame_path=Path(f"frame_{index}.jpg"),
                frame_index=index,
                total_frames=6,
                detections=detections,
                violations=violations,
                query_intent=intent,
                image_shape=(100, 100, 3),
            )
        )

    selected = select_ranked_frames(candidates, top_k=3)

    assert any(candidate.frame_index == 5 for candidate in selected)
    assert selected[0].frame_index == 5
    assert selected[0].selected_for == "violation_evidence"


def test_safe_mode_temporal_diversity_fills_low_information_frames():
    intent = parse_query_intent("driver without seatbelt")
    candidates = [
        score_frame_for_safe_mode(
            frame_path=Path(f"empty_{index}.jpg"),
            frame_index=index,
            total_frames=9,
            detections=[],
            violations=[],
            query_intent=intent,
            image_shape=(100, 100, 3),
        )
        for index in range(9)
    ]

    selected = select_ranked_frames(candidates, top_k=3)
    selected_indexes = {candidate.frame_index for candidate in selected}

    assert len(selected) == 3
    assert 0 in selected_indexes
    assert max(selected_indexes) >= 7
    assert any(candidate.selected_for == "temporal_diversity" for candidate in selected)


def test_safe_mode_pipeline_outputs_ranking_diagnostics(monkeypatch, tmp_path):
    import src.pipeline as pipeline_module

    frames = [tmp_path / f"frame_{index:06d}.jpg" for index in range(4)]
    for frame in frames:
        frame.write_bytes(b"placeholder")

    class FakeDetector:
        checkpoint = "checkpoints/yolov8s-seg.pt"

        def detect(self, image):  # noqa: ARG002
            current = str(pipeline_module._TEST_CURRENT_FRAME)
            if current.endswith("000003.jpg"):
                return [make_detection("person"), make_detection("torso", bbox=(20, 30, 80, 80))]
            return [make_detection("car", bbox=(45, 40, 55, 48))]

    def fake_imread(path):
        pipeline_module._TEST_CURRENT_FRAME = path
        return np.zeros((100, 100, 3), dtype=np.uint8)

    def fake_write(path, image):  # noqa: ARG001
        return None

    monkeypatch.setattr(pipeline_module.SETTINGS, "analysis_safe_mode", True)
    monkeypatch.setattr(pipeline_module.SETTINGS, "enable_vlm", False)
    monkeypatch.setattr(pipeline_module.SETTINGS, "mobile_sam_worker_enabled", False)
    monkeypatch.setattr(pipeline_module.SETTINGS, "top_k", 2)
    monkeypatch.setattr(pipeline_module.SETTINGS, "data_dir", tmp_path)
    monkeypatch.setattr(pipeline_module, "ClipEmbedder", lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("ClipEmbedder should not load")))
    monkeypatch.setattr(pipeline_module, "FaissIndex", lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("FaissIndex should not load")))
    monkeypatch.setattr(pipeline_module, "MobileSamSegmenter", lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("MobileSAM should not load")))
    monkeypatch.setattr(pipeline_module, "VlmReasoner", lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("VLM should not load")))
    monkeypatch.setattr(pipeline_module, "YoloDetector", FakeDetector)
    monkeypatch.setattr(pipeline_module, "imread_rgb", fake_imread)
    monkeypatch.setattr(pipeline_module, "imwrite_rgb", fake_write)
    monkeypatch.setattr(
        pipeline_module.SafeTracePipeline,
        "_collect_input_frames",
        lambda self, inputs, fps, max_frames, **kwargs: (frames, [], {"videos": 0, "images": 4}),  # noqa: ARG005
    )

    pipeline = pipeline_module.SafeTracePipeline()
    result = pipeline.run([frames[0]], query="driver without seatbelt", fps=1.0, k=2)

    assert result[0]["frame_path"].endswith("000003.jpg")
    metadata = result[0]["search_metadata"]
    assert metadata["mode"] == "safe_ranked_frame_scan"
    assert metadata["embeddingBypassed"] is True
    assert metadata["queryIntent"]["intents"] == ["seatbelt", "person"]
    assert metadata["selectedFor"] == "violation_evidence"
    assert "rankingReason" in metadata
    assert "detectedObjectSummary" in metadata
    assert pipeline.component_diagnostics["safeRankingFramesScanned"] == 4
    assert pipeline.component_diagnostics["safeRankingSelectedFrames"] == 2


def test_pipeline_explicit_mobile_sam_enablement_still_constructs_segmenter(monkeypatch):
    import src.pipeline as pipeline_module

    class FakeIndex:
        def __init__(self, embedder):  # noqa: ARG002
            pass

    constructed = {"mobile_sam": False}

    class FakeMobileSam:
        available = True

        def __init__(self):
            constructed["mobile_sam"] = True

        def refine(self, image, detections):  # noqa: ARG002
            return detections

    monkeypatch.setattr(pipeline_module.SETTINGS, "enable_vlm", False)
    monkeypatch.setattr(pipeline_module.SETTINGS, "mobile_sam_enabled", "auto")
    monkeypatch.setattr(pipeline_module, "ClipEmbedder", lambda: object())
    monkeypatch.setattr(pipeline_module, "FaissIndex", FakeIndex)
    monkeypatch.setattr(pipeline_module, "YoloDetector", lambda: object())
    monkeypatch.setattr(pipeline_module, "MobileSamSegmenter", FakeMobileSam)

    pipeline = pipeline_module.SafeTracePipeline()

    assert constructed["mobile_sam"] is True
    assert pipeline.segmenter.available is True


def test_pipeline_labels_local_vlm_source_by_selected_profile(monkeypatch):
    import src.pipeline as pipeline_module

    monkeypatch.setattr(pipeline_module.SETTINGS, "vlm_profile", "lightweight_256m")
    assert pipeline_module._profiled_explanation_source("vlm_local") == "vlm_lightweight"

    monkeypatch.setattr(pipeline_module.SETTINGS, "vlm_profile", "enhanced_2b")
    assert pipeline_module._profiled_explanation_source("vlm_local") == "vlm_enhanced"

    monkeypatch.setattr(pipeline_module.SETTINGS, "vlm_profile", "rule_based")
    assert pipeline_module._profiled_explanation_source("vlm_local") == "vlm_local"
    assert pipeline_module._profiled_explanation_source("rule_based") == "rule_based"


def test_ollama_vlm_success_uses_prompt_and_marks_source(monkeypatch):
    captured = {}

    def fake_post(url, json, timeout):  # noqa: ARG001
        captured["url"] = url
        captured["json"] = json
        captured["timeout"] = timeout
        return FakeGenerateResponse({"response": "A worker is visible with uncertain helmet evidence due to glare."})

    monkeypatch.setattr(vlm_reasoner.SETTINGS, "vlm_enabled", "auto")
    monkeypatch.setattr(vlm_reasoner.SETTINGS, "enable_vlm", True)
    monkeypatch.setattr(vlm_reasoner.SETTINGS, "vlm_provider", "ollama")
    monkeypatch.setattr(vlm_reasoner.SETTINGS, "vlm_ollama_base_url", "http://127.0.0.1:11434")
    monkeypatch.setattr(vlm_reasoner.SETTINGS, "vlm_model", "llava")
    monkeypatch.setattr(vlm_reasoner.SETTINGS, "vlm_timeout_seconds", 2.0)
    monkeypatch.setattr(vlm_reasoner.SETTINGS, "vlm_max_tokens", 90)
    monkeypatch.setattr(vlm_reasoner.httpx, "post", fake_post)

    reasoner = VlmReasoner(device="cpu", enabled=True)
    text = reasoner.explain_violation(np.zeros((4, 4, 3), dtype=np.uint8), [make_violation()])

    assert text.startswith("A worker is visible")
    assert reasoner.last_explanation_source == "vlm_ollama"
    assert captured["url"] == "http://127.0.0.1:11434/api/generate"
    assert VLM_PROMPT in captured["json"]["prompt"]
    assert captured["json"]["model"] == "llava"
    assert captured["json"]["images"]


def test_auto_vlm_prefers_existing_local_provider_without_ollama(monkeypatch, tmp_path):
    def fail_if_ollama_called(*args, **kwargs):  # noqa: ARG001
        raise AssertionError("auto should prefer the existing local VLM provider")

    def fake_load(self):
        self.provider = "local"
        self._loaded = True

    def fake_local_explain(self, image, violations):  # noqa: ARG001
        self.last_explanation_source = "vlm_local"
        return "Local provider sees limited helmet evidence; review glare and angle."

    model_dir = tmp_path / "vlm_model"
    model_dir.mkdir()
    (model_dir / "config.json").write_text("{}", encoding="utf-8")
    monkeypatch.setattr(vlm_reasoner.SETTINGS, "vlm_enabled", "auto")
    monkeypatch.setattr(vlm_reasoner.SETTINGS, "enable_vlm", True)
    monkeypatch.setattr(vlm_reasoner.SETTINGS, "vlm_provider", "auto")
    monkeypatch.setattr(vlm_reasoner.SETTINGS, "vlm_model_dir", model_dir)
    monkeypatch.setattr(vlm_reasoner, "_local_transformer_available", lambda model_dir: True)  # noqa: ARG005
    monkeypatch.setattr(vlm_reasoner.VlmReasoner, "_load_transformer_provider", fake_load)
    monkeypatch.setattr(vlm_reasoner.VlmReasoner, "_explain_with_transformers", fake_local_explain)
    monkeypatch.setattr(vlm_reasoner.httpx, "post", fail_if_ollama_called)

    reasoner = VlmReasoner(device="cpu", enabled=True)
    text = reasoner.explain_violation(np.zeros((4, 4, 3), dtype=np.uint8), [make_violation()])

    assert reasoner.provider == "local"
    assert reasoner.last_explanation_source == "vlm_local"
    assert text.startswith("Local provider")


def test_auto_vlm_uses_rule_based_when_no_provider_is_available(monkeypatch, tmp_path):
    def fake_get(*args, **kwargs):  # noqa: ARG001
        raise httpx.ConnectError("ollama offline")

    def fail_if_generation_called(*args, **kwargs):  # noqa: ARG001
        raise AssertionError("auto should not call Ollama generation when status is unavailable")

    missing_model_dir = tmp_path / "missing_vlm_model"
    monkeypatch.setattr(vlm_reasoner.SETTINGS, "vlm_enabled", "auto")
    monkeypatch.setattr(vlm_reasoner.SETTINGS, "enable_vlm", True)
    monkeypatch.setattr(vlm_reasoner.SETTINGS, "vlm_provider", "auto")
    monkeypatch.setattr(vlm_reasoner.SETTINGS, "vlm_model_dir", missing_model_dir)
    monkeypatch.setattr(vlm_reasoner.SETTINGS, "vlm_ollama_base_url", "http://127.0.0.1:11434")
    monkeypatch.setattr(vlm_reasoner.httpx, "get", fake_get)
    monkeypatch.setattr(vlm_reasoner.httpx, "post", fail_if_generation_called)

    reasoner = VlmReasoner(device="cpu", enabled=True)
    text = reasoner.explain_violation(np.zeros((4, 4, 3), dtype=np.uint8), [make_violation()])

    assert reasoner.provider == "rule_based"
    assert reasoner.last_explanation_source == "rule_based"
    assert "Rule-based explanation" in text


def test_ollama_timeout_falls_back_to_rule_based(monkeypatch):
    def fake_post(*args, **kwargs):  # noqa: ARG001
        raise httpx.TimeoutException("slow local model")

    monkeypatch.setattr(vlm_reasoner.SETTINGS, "vlm_enabled", "auto")
    monkeypatch.setattr(vlm_reasoner.SETTINGS, "enable_vlm", True)
    monkeypatch.setattr(vlm_reasoner.SETTINGS, "vlm_provider", "ollama")
    monkeypatch.setattr(vlm_reasoner.SETTINGS, "vlm_ollama_base_url", "http://127.0.0.1:11434")
    monkeypatch.setattr(vlm_reasoner.httpx, "post", fake_post)

    reasoner = VlmReasoner(device="cpu", enabled=True)
    text = reasoner.explain_violation(np.zeros((4, 4, 3), dtype=np.uint8), [make_violation()])

    assert reasoner.last_explanation_source == "rule_based"
    assert "Rule-based explanation" in text


def test_transformer_vlm_uses_chat_template_image_content(monkeypatch):
    monkeypatch.setattr(vlm_reasoner.SETTINGS, "vlm_max_tokens", 16)
    processor = FakeChatTemplateProcessor()
    model = FakeLocalModel()
    reasoner = make_local_reasoner(processor, model)

    text = reasoner._explain_with_transformers(
        np.zeros((4, 4, 3), dtype=np.uint8),
        [make_violation()],
    )

    assert text.startswith("Visible helmet evidence")
    assert reasoner.last_explanation_source == "vlm_local"
    assert processor.messages == [
        {
            "role": "user",
            "content": [
                {"type": "image"},
                {"type": "text", "text": reasoner._prompt_for([make_violation()])},
            ],
        }
    ]
    assert processor.template_kwargs["add_generation_prompt"] is True
    assert processor.call_kwargs["images"]
    assert isinstance(processor.call_kwargs["images"], list)
    assert "<image>" in processor.call_kwargs["text"]
    assert processor.decode_output_ids == [[4]]
    assert processor.decode_kwargs["skip_special_tokens"] is True
    assert model.generate_kwargs["max_new_tokens"] == 16
    assert model.generate_kwargs["do_sample"] is False


def test_transformer_vlm_fallback_prompt_keeps_image_token(monkeypatch):
    monkeypatch.setattr(vlm_reasoner.SETTINGS, "vlm_max_tokens", 16)
    processor = FakeNoTemplateProcessor()
    model = FakeLocalModel()
    reasoner = make_local_reasoner(processor, model)

    text = reasoner._explain_with_transformers(
        np.zeros((4, 4, 3), dtype=np.uint8),
        [make_violation()],
    )

    assert text.startswith("Visible helmet evidence")
    assert reasoner.last_explanation_source == "vlm_local"
    assert processor.call_kwargs["text"].startswith("<image>\n")
    assert isinstance(processor.call_kwargs["images"], list)


def test_transformer_vlm_generation_failure_returns_rule_based(monkeypatch):
    monkeypatch.setattr(vlm_reasoner.SETTINGS, "vlm_max_tokens", 16)
    processor = FakeChatTemplateProcessor()
    model = FakeLocalModel(fail=True)
    reasoner = make_local_reasoner(processor, model)

    text = reasoner._explain_with_transformers(
        np.zeros((4, 4, 3), dtype=np.uint8),
        [make_violation()],
    )

    assert reasoner.last_explanation_source == "rule_based"
    assert "Rule-based explanation" in text


def test_transformer_vlm_timeout_returns_rule_based(monkeypatch):
    def fake_timeout(callable_obj, timeout_seconds):  # noqa: ARG001
        raise TimeoutError("slow local VLM")

    monkeypatch.setattr(vlm_reasoner.SETTINGS, "vlm_timeout_seconds", 0.01)
    monkeypatch.setattr(vlm_reasoner, "_run_with_timeout", fake_timeout)
    processor = FakeChatTemplateProcessor()
    model = FakeLocalModel()
    reasoner = make_local_reasoner(processor, model)

    text = reasoner._explain_with_transformers(
        np.zeros((4, 4, 3), dtype=np.uint8),
        [make_violation()],
    )

    assert reasoner.last_explanation_source == "rule_based"
    assert "Rule-based explanation" in text


def test_pipeline_caps_local_vlm_explanation_attempts(monkeypatch, tmp_path):
    import src.pipeline as pipeline_module

    class FakeDetector:
        def detect(self, image):  # noqa: ARG002
            return []

    class FakeSegmenter:
        def refine(self, image, detections):  # noqa: ARG002
            return detections

    class FakeVlm:
        provider = "local"
        enabled = True

        def __init__(self):
            self.count = 0
            self.last_explanation_source = "rule_based"

        def explain_violation(self, image, violations):  # noqa: ARG002
            self.count += 1
            self.last_explanation_source = "vlm_local"
            return "Local VLM sees visible helmet evidence with uncertainty."

    fake_vlm = FakeVlm()
    monkeypatch.setattr(pipeline_module.SETTINGS, "vlm_max_frames", 1)
    monkeypatch.setattr(pipeline_module.SETTINGS, "vlm_profile", "lightweight_256m")
    monkeypatch.setattr(pipeline_module, "imread_rgb", lambda path: np.zeros((4, 4, 3), dtype=np.uint8))
    monkeypatch.setattr(pipeline_module, "evaluate_rules", lambda detections: [make_violation()])

    pipeline = pipeline_module.SafeTracePipeline(
        embedder=object(),
        index=object(),
        detector=FakeDetector(),
        segmenter=FakeSegmenter(),
        vlm=fake_vlm,
    )

    first = pipeline.analyze_frame(tmp_path / "frame1.jpg")
    second = pipeline.analyze_frame(tmp_path / "frame2.jpg")

    assert fake_vlm.count == 1
    assert first.explanation_source == "vlm_lightweight"
    assert second.explanation_source == "rule_based"
    assert "Rule-based explanation" in second.explanation


def test_sanitize_vlm_output_removes_prompt_echo_and_role_labels():
    prompt = "Describe only visible safety evidence in this frame.\nFindings to inspect: helmet_missing."
    raw = "User: <image>\nDescribe only visible safety evidence in this frame.\nAssistant: A worker is visible without clear helmet evidence due to glare."

    clean = sanitize_vlm_output(raw, prompt)

    assert clean == "A worker is visible without clear helmet evidence due to glare."
    assert is_useful_vlm_output(clean)


def test_prompt_echo_unclear_output_falls_back_to_rule_based(monkeypatch):
    monkeypatch.setattr(vlm_reasoner.SETTINGS, "vlm_max_tokens", 16)
    processor = FakeChatTemplateProcessor(
        "User: <image>\nDescribe only visible safety evidence in this frame.\nAssistant: Unclear."
    )
    model = FakeLocalModel()
    reasoner = make_local_reasoner(processor, model)

    text = reasoner._explain_with_transformers(
        np.zeros((4, 4, 3), dtype=np.uint8),
        [make_violation()],
    )

    assert reasoner.last_explanation_source == "rule_based"
    assert "Rule-based explanation" in text


def test_token_leaking_output_is_sanitized_when_still_useful(monkeypatch):
    monkeypatch.setattr(vlm_reasoner.SETTINGS, "vlm_max_tokens", 16)
    processor = FakeChatTemplateProcessor(
        "<global-img> <row_1_col_1> A worker is visible without helmet evidence, but glare creates uncertainty."
    )
    model = FakeLocalModel()
    reasoner = make_local_reasoner(processor, model)

    text = reasoner._explain_with_transformers(
        np.zeros((4, 4, 3), dtype=np.uint8),
        [make_violation()],
    )

    assert reasoner.last_explanation_source == "vlm_local"
    assert text == "A worker is visible without helmet evidence, but glare creates uncertainty."
    assert "<" not in text


def test_generic_vlm_output_falls_back_to_rule_based(monkeypatch):
    monkeypatch.setattr(vlm_reasoner.SETTINGS, "vlm_max_tokens", 16)
    processor = FakeChatTemplateProcessor("Safety evidence missing.")
    model = FakeLocalModel()
    reasoner = make_local_reasoner(processor, model)

    text = reasoner._explain_with_transformers(
        np.zeros((4, 4, 3), dtype=np.uint8),
        [make_violation()],
    )

    assert reasoner.last_explanation_source == "rule_based"
    assert "Rule-based explanation" in text
