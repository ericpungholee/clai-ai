import json
from pathlib import Path

import pytest
from scripts.report_drift_regression import report

MANIFEST_PATH = Path(__file__).parent / "fixtures" / "drift-corpus-manifest.json"


def test_regression_report_stays_operation_specific_without_quality_thresholds() -> (
    None
):
    manifest = json.loads(MANIFEST_PATH.read_text())
    rows = [
        {
            "image_id": pair["fixture_id"],
            "edit_id": pair["operation"],
            "cosine_similarity": pair["score"],
        }
        for pair in manifest["pairs"]
    ]
    summary = report(manifest, {"rows": rows})
    assert all(op["mean_delta"] == 0 for op in summary["operations"].values())
    rows[0]["cosine_similarity"] = 0.5
    changed = report(manifest, {"rows": rows})
    assert changed["operations"][rows[0]["edit_id"]]["largest_pair_delta"] > 0
    assert "threshold" not in json.dumps(changed)
    with pytest.raises(ValueError, match="100 saved pairs"):
        report(manifest, {"rows": rows[:-1]})


def test_drift_manifest_indexes_the_complete_saved_corpus() -> None:
    manifest = json.loads(MANIFEST_PATH.read_text())

    assert manifest["corpus_id"] == "clai-p0-zero-2026-09-03"
    assert len(manifest["fixtures"]) == 20
    assert len(manifest["pairs"]) == 100
    assert set(manifest["operation_baselines"]) == {
        "material",
        "recolor",
        "relight",
        "remove",
        "restage",
    }
    assert all(
        baseline["count"] == 20 for baseline in manifest["operation_baselines"].values()
    )


def test_shoe_recolor_acceptance_baseline_is_operation_specific() -> None:
    manifest = json.loads(MANIFEST_PATH.read_text())
    baseline = manifest["p0_shoe_recolor_baseline"]

    assert baseline["count"] == 5
    assert baseline["mean"] == 0.9300877690315247
    assert baseline["min"] == 0.8492327928543091
    assert baseline["max"] == 0.9792041182518005
    assert manifest["scorer"]["meaning"] == (
        "operation-specific change magnitude, not correctness"
    )


def test_every_pair_records_prompts_scores_and_external_locations() -> None:
    manifest = json.loads(MANIFEST_PATH.read_text())

    for pair in manifest["pairs"]:
        assert pair["fixture_name"]
        assert pair["operation"]
        assert pair["user_prompt"]
        assert pair["prompt_at_runtime"]
        assert 0 <= pair["score"] <= 1
        assert pair["input_external_url"].startswith("https://")
        assert pair["output_external_url"].startswith("https://")
