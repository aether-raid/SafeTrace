import importlib
import json

from src.detector_utils import resolve_detector_checkpoint


def test_custom_detector_missing_falls_back_to_default(workspace_tmp):
    default = workspace_tmp / "default.pt"
    fallback = workspace_tmp / "fallback.pt"
    missing_custom = workspace_tmp / "custom.pt"
    default.write_text("weights", encoding="utf-8")

    chosen = resolve_detector_checkpoint(
        custom_checkpoint=missing_custom,
        default_checkpoint=default,
        fallback_checkpoint=fallback,
    )

    assert chosen == default


def test_detector_class_mapping_json(monkeypatch):
    monkeypatch.setenv(
        "SAFETRACE_DETECTOR_CLASSES",
        json.dumps(
            {
                "classes": {"0": "seatbelt", "1": "hand"},
                "aliases": {"face": ["driver face"]},
            }
        ),
    )
    import src.config as config

    reloaded = importlib.reload(config)

    assert reloaded.normalize_label("anything", class_id=0) == "seatbelt"
    assert reloaded.normalize_label("driver face") == "face"
