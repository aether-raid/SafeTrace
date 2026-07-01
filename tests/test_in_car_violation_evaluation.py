import json

from scripts.evaluate_in_car_violations import evaluate_capabilities


def test_in_car_evaluation_reports_not_tested_without_samples(tmp_path):
    results = evaluate_capabilities(tmp_path / "missing")

    assert {result.status for result in results} == {"NOT_TESTED_NO_SAMPLE"}
    assert {result.key for result in results} >= {
        "missing_seatbelt",
        "phone_usage_while_driving",
        "missing_helmet",
    }


def test_in_car_evaluation_detects_capability_from_result_json(tmp_path):
    sample = tmp_path / "seatbelt_result.json"
    sample.write_text(
        json.dumps(
            {
                "jobId": "job_eval",
                "frames": [
                    {
                        "violations": [
                            {
                                "id": "seatbelt_missing",
                                "name": "Missing Seatbelt",
                                "severity": "high",
                                "confidence": 0.91,
                            }
                        ]
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    results = {result.key: result for result in evaluate_capabilities(tmp_path)}

    assert results["missing_seatbelt"].status == "PASS"
    assert str(sample) in results["missing_seatbelt"].evidence_files
    assert results["phone_usage_while_driving"].status == "UNSUPPORTED"
