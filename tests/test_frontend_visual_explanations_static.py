from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def read_frontend(path: str) -> str:
    return (ROOT / "frontend-react" / "src" / path).read_text(encoding="utf-8")


def test_sidebar_separates_visual_explanations_from_enhanced_vlm():
    source = read_frontend("components/Sidebar.tsx")

    assert "Visual explanations" in source
    assert "Enhanced VLM" in source
    assert "Visual explanations are on. SafeTrace will use VLM when available" in source
    assert "Enhanced VLM unavailable. Rule-based explanations are still active." in source
    assert "disabled={vlmUnavailable}" not in source
    assert "onClick={() => updateSettings({ visualExplanations: !showVisualExplanations })}" in source
    assert "onClick={() => updateSettings({ enhancedVlmExplanations: !useEnhancedVlmExplanations })}" in source


def test_app_uses_visual_toggle_for_display_and_enhanced_toggle_for_backend_vlm():
    source = read_frontend("App.tsx")

    assert "visualExplanations: true" in source
    assert "enhancedVlmExplanations: true" in source
    assert "enableVlm: settings.enhancedVlmExplanations" in source
    assert "showExplanations={settings.visualExplanations}" in source


def test_evidence_cards_use_two_explanation_source_labels():
    source = read_frontend("components/FrameEvidenceCard.tsx")

    assert "'VLM explanation'" in source
    assert "'Rule-based explanation'" in source
    assert "VLM explanation: local provider" not in source
    assert "VLM explanation: Ollama" not in source
