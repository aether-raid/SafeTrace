from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_safety_insights_report_helpers_include_required_fields():
    source = (ROOT / "frontend-react" / "src" / "components" / "SafetyInsightsDashboard.tsx").read_text(
        encoding="utf-8"
    )

    for field in (
        "video",
        "jobId",
        "status",
        "violationType",
        "severity",
        "frameNumber",
        "timestamp",
        "confidence",
        "evidenceCount",
        "topFinding",
        "updatedAt",
        "completedAt",
    ):
        assert field in source

    assert "export function buildSafetyInsightsReportRows" in source
    assert "export function buildSafetyInsightsCsv" in source
    assert "export function buildSafetyInsightsMarkdown" in source
    assert "export function buildSafetyInsightsJson" in source
    assert "Raw uploaded videos" in source
    assert "copied evidence image bytes" in source
