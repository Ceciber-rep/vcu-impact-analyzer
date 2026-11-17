"""Pipeline, cache and CLI tests. Offline: no model is ever called."""

import sys
from pathlib import Path

import pytest

from vcu_impact import cache, pipeline, spec_editor
from vcu_impact.analysis import AnalysisRun
from vcu_impact.cli import main as cli_main
from vcu_impact.llm import LLMConfig, extract_json
from vcu_impact.models import LLMImpactResult
from vcu_impact.pipeline import InputFile, Inputs, analyze, build_rows, default_inputs, prepare

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "eval"))
from evaluate import load_dataset, scenario_path  # noqa: E402


@pytest.fixture(autouse=True)
def isolated(monkeypatch, tmp_path):
    """No configured model and an empty local cache in every test."""
    for var in ("LLM_PROVIDER", "LLM_FALLBACK_PROVIDER"):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setattr(cache, "LOCAL_CACHE_DIR", tmp_path / "cache")


def _with_revised(data: bytes, name: str = "edited.docx") -> Inputs:
    d = default_inputs()
    return Inputs(baseline=d.baseline, revised=InputFile(name, data), register=d.register)


def _edited_revised(edit) -> Inputs:
    doc = spec_editor.load(default_inputs().revised.data)
    edit(doc)
    return _with_revised(spec_editor.to_bytes(doc))


def _canned_run(prep, model_label="fake:model") -> AnalysisRun:
    result = LLMImpactResult.model_validate(
        {
            "change_interpretations": [
                {"requirement_id": c.req_id, "nature": "tightened", "engineering_summary": "s"}
                for c in prep.diff.requirement_changes
            ],
            "assessments": [
                {
                    "test_id": t.test_id,
                    "status": "not_affected",
                    "confidence": "low",
                    "related_requirements": [],
                    "required_actions": ["none"],
                    "reason": "r",
                    "evidence": [],
                    "recommended_action": "x",
                }
                for t in prep.register.tests
            ],
        }
    )
    return AnalysisRun(model_label=model_label, result=result)


def test_default_inputs_replay_real_recording():
    prep = prepare(default_inputs())
    out = analyze(prep, mode="replay")
    assert out.mode == "replay" and "No model was called" in out.source_text
    rows = build_rows(prep, out)
    assert len(rows) == 12 and all(r.assessment for r in rows)
    tv001 = next(r for r in rows if r.test.test_id == "TV-001")
    assert tv001.assessment.status == "directly_affected"


def test_every_scenario_has_a_committed_recording():
    for sc in load_dataset()["scenarios"]:
        d = default_inputs()
        prep = prepare(Inputs(d.baseline, InputFile.from_path(scenario_path(sc)), d.register))
        found = cache.find(prep.key)
        assert found and found[1] == "recorded", sc["id"]


def test_replay_reapplies_post_checks_and_corrects_the_s5_status():
    sc = next(s for s in load_dataset()["scenarios"] if s["id"] == "S5")
    d = default_inputs()
    prep = prepare(Inputs(d.baseline, InputFile.from_path(scenario_path(sc)), d.register))
    out = analyze(prep, mode="replay")
    # The recorded raw output says directly_affected; the post-check corrects it visibly.
    recorded_raw = next(
        a
        for a in LLMImpactResult.model_validate_json(extract_json(out.run.raw_text)).assessments
        if a.test_id == "TV-005"
    )
    assert recorded_raw.status == "directly_affected"
    tv005 = next(r for r in build_rows(prep, out) if r.test.test_id == "TV-005")
    assert tv005.assessment.status == "not_affected"
    assert tv005.adjustment and tv005.adjustment.original_status == "directly_affected"
    assert any("changed from directly_affected to not_affected" in w for w in tv005.warnings)
    assert [a.test_id for a in out.run.adjustments] == ["TV-005"]  # nothing else is adjusted


def test_key_is_stable_and_changes_with_any_edit():
    assert prepare(default_inputs()).key == prepare(default_inputs()).key
    edited = _edited_revised(lambda doc: spec_editor.replace_in_requirement(doc, "VCU-DR-01", "80", "90"))
    assert prepare(edited).key != prepare(default_inputs()).key


def test_file_names_do_not_affect_the_key():
    d = default_inputs()
    renamed = _with_revised(d.revised.data, "renamed.docx")
    assert prepare(renamed).key == prepare(d).key


def test_no_requirement_change_is_not_analysed():
    d = default_inputs()
    prep = prepare(_with_revised(d.baseline.data, "same.docx"))
    out = analyze(prep)
    assert out.mode == "not_analysed" and "nothing to assess" in out.reason
    assert all(r.assessment is None for r in build_rows(prep, out))


def test_unseen_edit_without_model_is_not_analysed():
    prep = prepare(_edited_revised(lambda doc: spec_editor.replace_in_requirement(doc, "VCU-DR-01", "80", "90")))
    out = analyze(prep)
    assert out.mode == "not_analysed" and "LLM_PROVIDER" in out.reason
    assert analyze(prep, mode="replay").mode == "not_analysed"


def test_live_falls_back_and_caches(monkeypatch):
    prep = prepare(_edited_revised(lambda doc: spec_editor.replace_in_requirement(doc, "VCU-DR-01", "80", "90")))
    primary = LLMConfig(provider="groq", model="primary", api_key="x")
    fallback = LLMConfig(provider="gemini", model="fallback", api_key="x")
    monkeypatch.setattr(pipeline, "configured_llms", lambda: ([primary, fallback], []))

    def fake_run(client, diff, revised, register):
        if client.config.model == "primary":
            raise RuntimeError("429 rate limit")
        return _canned_run(prep, client.config.label)

    monkeypatch.setattr(pipeline, "run_analysis", fake_run)
    out = analyze(prep, mode="live")
    assert out.mode == "live" and out.model_label == "gemini:fallback"
    assert any("groq:primary failed" in w for w in out.run.warnings)
    # The live result is cached locally: the next auto run does not call a model.
    monkeypatch.setattr(pipeline, "run_analysis", lambda *a: pytest.fail("model called again"))
    again = analyze(prep)
    assert again.mode == "cached" and again.model_label == "gemini:fallback"


def test_all_models_failing_is_reported(monkeypatch):
    prep = prepare(_edited_revised(lambda doc: spec_editor.replace_in_requirement(doc, "VCU-DR-01", "80", "90")))
    monkeypatch.setattr(pipeline, "configured_llms", lambda: ([LLMConfig("groq", "m", "x")], []))
    monkeypatch.setattr(pipeline, "run_analysis", lambda *a: (_ for _ in ()).throw(RuntimeError("down")))
    out = analyze(prep, mode="live")
    assert out.mode == "not_analysed" and "down" in out.reason


def test_cli_replay(capsys):
    assert cli_main(["analyze", "--mode", "replay"]) == 0
    printed = capsys.readouterr().out
    assert "Replayed" in printed and "TV-012" in printed and "final approval" in printed
