"""Scoring tests that run on the stored evaluation results (offline)."""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "eval"))
from evaluate import (  # noqa: E402
    RESULTS,
    _is_rate_limit,
    held_out_scenarios,
    load_dataset,
    original_scenarios,
    register_path,
    score_model,
)

from vcu_impact.register_parser import parse_register  # noqa: E402
from vcu_impact.spec_parser import parse_spec  # noqa: E402

QWEN_V3 = RESULTS / "v3" / "groq-qwen3.8-27b"


def test_raw_and_postcheck_views_are_kept_apart_on_stored_runs():
    data = load_dataset()
    original = original_scenarios(data)
    raw = score_model(QWEN_V3, original, "v3", postcheck=False)
    checked = score_model(QWEN_V3, original, "v3", postcheck=True)
    # Raw: the model's own statuses, S5 TV-005 is its known contradiction.
    assert raw["critical_correct"] == 15 and raw["adjustments"] == []
    assert raw["critical_failures"] == ["S5 TV-005: got D, expected N/P"]
    # Post-check: the same stored output, with exactly that status corrected.
    assert checked["critical_correct"] == 16 and checked["adjustments"] == ["S5 TV-005"]
    assert checked["lenient_correct"] == raw["lenient_correct"] + 1
    assert checked["missed_impacts"] == raw["missed_impacts"] == 0


def test_labels_cover_exactly_the_tests_of_each_scenario_register():
    """No scenario may rely on a fixed number of tests (S10 has 13)."""
    data = load_dataset()
    baseline = parse_spec(ROOT / "data" / "input" / "VCU_Spec_Baseline.docx")
    for sc in data["scenarios"]:
        revised = (
            parse_spec(ROOT / "data" / "input" / "VCU_Spec_Revised.docx") if sc.get("source") == "revised" else None
        )
        if revised is None:
            from evaluate import scenario_path

            revised = parse_spec(scenario_path(sc))
        register = parse_register(register_path(sc), revised, baseline)
        assert set(sc["tests"]) == {t.test_id for t in register.tests}, sc["id"]


def test_held_out_scenarios_are_separate_from_the_original_cells():
    data = load_dataset()
    original, held = original_scenarios(data), held_out_scenarios(data)
    assert sum(len(sc["tests"]) for sc in original) == 84
    assert {sc["id"] for sc in original}.isdisjoint({sc["id"] for sc in held})


def test_groq_tpm_413_is_treated_as_a_rate_limit():
    tpm = (
        "APIStatusError: Error code: 413 - Request too large for model `openai/gpt-oss-120b` on tokens per "
        "minute (TPM): Limit 8000, Requested 8231, please reduce your message size and try again."
    )
    assert _is_rate_limit(tpm)
    assert _is_rate_limit("InternalServerError: Error code: 503 - UNAVAILABLE")
    assert not _is_rate_limit("ValidationError: 1 validation error for LLMImpactResult")
