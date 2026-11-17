"""Tests for the deterministic core: parsing, diffing, editing and post-checks."""

from pathlib import Path

import pytest

from vcu_impact import models, spec_editor
from vcu_impact.analysis import AnalysisRun, approval_language, normalize_actions, post_check
from vcu_impact.diff import diff_specs, numeric_changes, word_diff
from vcu_impact.models import (
    ChangeType,
    ImpactStatus,
    LinkStatus,
    LLMImpactResult,
    RequiredAction,
)
from vcu_impact.register_parser import classify_links, parse_register
from vcu_impact.spec_parser import parse_spec

INPUT = Path(__file__).resolve().parents[1] / "data" / "input"
BASELINE = INPUT / "VCU_Spec_Baseline.docx"
REVISED = INPUT / "VCU_Spec_Revised.docx"
REGISTER = INPUT / "VCU_Test_Register.xlsx"
ALL_IDS = ["VCU-DR-01", "VCU-DR-02", "VCU-BRK-03", "VCU-DGN-04", "VCU-LOG-05", "VCU-MOD-06"]


@pytest.fixture(scope="module")
def baseline():
    return parse_spec(BASELINE)


@pytest.fixture(scope="module")
def revised():
    return parse_spec(REVISED)


def _edited(edit) -> bytes:
    doc = spec_editor.load(BASELINE)
    edit(doc)
    return spec_editor.to_bytes(doc)


# -- spec parser ---------------------------------------------------------------


def test_parses_all_requirements(baseline, revised):
    assert baseline.requirement_ids == ALL_IDS
    assert revised.requirement_ids == ALL_IDS
    dr01 = baseline.requirement("VCU-DR-01")
    assert dr01.title == "Driver torque response"
    assert "within 100 milliseconds" in dr01.text
    assert baseline.revision.startswith("Revision A")
    assert revised.revision.startswith("Revision B")


# -- diff ------------------------------------------------------------------------


def test_real_revision_diff(baseline, revised):
    d = diff_specs(baseline, revised)
    assert [c.req_id for c in d.requirement_changes] == ["VCU-DR-01"]
    change = d.requirement_changes[0]
    assert change.change_type == ChangeType.MODIFIED
    assert [(n.unit, n.old_value, n.new_value) for n in change.numeric_changes] == [("ms", 100, 80)]
    assert set(d.unchanged_requirement_ids) == set(ALL_IDS) - {"VCU-DR-01"}
    assert "4 Revision notes" in {s.name for s in d.section_changes}


def test_identical_specs_have_no_changes(baseline):
    d = diff_specs(baseline, parse_spec(BASELINE))
    assert d.requirement_changes == [] and d.section_changes == []


def test_added_removed_and_reworded(baseline):
    def edit(doc):
        spec_editor.remove_requirement(doc, "VCU-MOD-06")
        spec_editor.add_requirement(doc, "VCU-LOG-05", "VCU-THM-07", "Thermal derating", "Torque shall be derated.")
        spec_editor.set_requirement(doc, "VCU-DGN-04", text="When the wheel-speed signal is lost, degrade.")
        spec_editor.set_requirement(doc, "VCU-DR-02", title="Pedal plausibility")

    revised = parse_spec(_edited(edit))
    kinds = {c.req_id: c for c in diff_specs(baseline, revised).requirement_changes}
    assert kinds["VCU-MOD-06"].change_type == ChangeType.REMOVED
    assert kinds["VCU-THM-07"].change_type == ChangeType.ADDED
    assert kinds["VCU-THM-07"].new.title == "Thermal derating"
    assert kinds["VCU-DGN-04"].change_type == ChangeType.MODIFIED
    assert kinds["VCU-DR-02"].title_changed and kinds["VCU-DR-02"].numeric_changes == []
    # The new requirement sits right after LOG-05 in document order.
    assert revised.requirement_ids.index("VCU-THM-07") == revised.requirement_ids.index("VCU-LOG-05") + 1


def test_numeric_changes_pair_by_unit():
    changes = numeric_changes("above 70% within 100 ms", "above 75% within 100 ms")
    assert [(c.unit, c.old_value, c.new_value) for c in changes] == [("%", 70, 75)]
    added = numeric_changes("priority", "priority within 80 milliseconds")
    assert added[0].old_value is None and added[0].new_value == 80


def test_word_diff_marks_only_changed_words():
    segs = word_diff("within 100 milliseconds", "within 80 milliseconds")
    assert ("delete", "100") in segs and ("insert", "80") in segs
    assert "".join(t for op, t in segs if op != "delete") == "within 80 milliseconds"


def test_whitespace_only_edit_is_not_a_change(baseline):
    text = baseline.requirement("VCU-DR-02").text
    spaced = "  " + text.replace(" ", "  ")
    revised = parse_spec(_edited(lambda d: spec_editor.set_requirement(d, "VCU-DR-02", text=spaced)))
    assert diff_specs(baseline, revised).requirement_changes == []


# -- register ----------------------------------------------------------------------


def test_register_links_and_values(baseline, revised):
    reg = parse_register(REGISTER, revised, baseline)
    tests = {t.test_id: t for t in reg.tests}
    assert len(tests) == 12 and len(reg.notes) == 5
    assert [link.status for link in tests["TV-002"].links] == [LinkStatus.VALID, LinkStatus.VALID]
    assert tests["TV-003"].links[0].status == LinkStatus.MISSING
    assert tests["TV-007"].links[0].status == LinkStatus.TBD
    assert tests["TV-008"].links[0].status == LinkStatus.UNKNOWN
    assert tests["TV-007"].result_verdict == "NOT RUN"
    assert (94.0, "ms", "result") in [(m.value, m.unit, m.source) for m in tests["TV-001"].measurements]
    assert {75.0, 95.0} <= {m.value for m in tests["TV-003"].measurements if m.unit == "%"}
    assert "different clocks" in reg.notes[1].observation


def test_link_to_removed_requirement(baseline):
    revised = parse_spec(_edited(lambda d: spec_editor.remove_requirement(d, "VCU-MOD-06")))
    assert classify_links("VCU-MOD-06", revised, baseline)[0].status == LinkStatus.REMOVED


# -- post-checks ---------------------------------------------------------------------


def test_post_check_fills_missing_and_strips_invented_ids(baseline, revised):
    reg = parse_register(REGISTER, revised, baseline)
    d = diff_specs(baseline, revised)
    raw = LLMImpactResult.model_validate(
        {
            "change_interpretations": [],
            "assessments": [
                {
                    "test_id": "TV-001",
                    "status": "directly_affected",
                    "confidence": "high",
                    "related_requirements": ["VCU-DR-01", "VCU-XYZ-99"],
                    "required_actions": ["rerun", "fix_link"],
                    "reason": "94 ms > 80 ms.",
                    "evidence": [],
                    "recommended_action": "Re-run.",
                },
                {
                    "test_id": "TV-999",
                    "status": "not_affected",
                    "confidence": "high",
                    "related_requirements": [],
                    "required_actions": ["none"],
                    "reason": "x",
                    "evidence": [],
                    "recommended_action": "x",
                },
            ],
        }
    )
    cleaned, warnings, _ = post_check(raw, d, reg)
    assert [a.test_id for a in cleaned.assessments] == [t.test_id for t in reg.tests]
    assert cleaned.assessments[0].related_requirements == ["VCU-DR-01"]
    assert cleaned.assessments[1].status == "needs_human_review"
    # TV-001 has a valid link: fix_link set by the LLM is removed.
    assert cleaned.assessments[0].required_actions == ["rerun"]
    assert any("removed fix_link" in w for w in warnings)
    # TV-003 (empty link) was omitted by the LLM: filled with owner_decision + fix_link.
    tv003 = next(a for a in cleaned.assessments if a.test_id == "TV-003")
    assert tv003.required_actions == ["fix_link", "owner_decision"]
    assert any("TV-999" in w for w in warnings)
    assert any("no interpretation" in w for w in warnings)


def test_approval_language_detector():
    assert approval_language("The test is approved for release.")
    assert not approval_language("This is not approved; final approval remains with the owner.")
    assert not approval_language("Previous result cannot be approved without re-run.")


def test_normalize_actions_rules():
    w: list[str] = []
    # Broken link adds fix_link and drops "none".
    assert normalize_actions("T", ImpactStatus.NOT_AFFECTED, [RequiredAction.NONE], True, w) == ["fix_link"]
    # Empty list becomes ["none"].
    assert normalize_actions("T", ImpactStatus.NOT_AFFECTED, [], False, w) == ["none"]
    # Canonical order, duplicates removed.
    acts = [RequiredAction.UPDATE_PROCEDURE, RequiredAction.RERUN, RequiredAction.RERUN]
    assert normalize_actions("T", ImpactStatus.DIRECTLY_AFFECTED, acts, False, w) == ["rerun", "update_procedure"]
    assert w == []
    # A contradiction is kept but flagged.
    normalize_actions("T", ImpactStatus.NOT_AFFECTED, [RequiredAction.RERUN], False, w)
    assert len(w) == 1 and "not_affected" in w[0]


# -- rewording safety net (analysis.post_check) ---------------------------------------


def _assessment(test_id, status, related, actions=("none",)):
    return {
        "test_id": test_id,
        "status": status,
        "confidence": "high",
        "related_requirements": list(related),
        "required_actions": list(actions),
        "reason": "the model's reason",
        "evidence": [],
        "recommended_action": "x",
    }


def _interp(req_id, nature):
    return {"requirement_id": req_id, "nature": nature, "engineering_summary": "s"}


@pytest.fixture(scope="module")
def reworded_and_tightened(baseline):
    """DGN-04 reworded (same meaning) and DR-01 changed to 90 ms: two changed requirements."""

    def edit(doc):
        spec_editor.set_requirement(doc, "VCU-DGN-04", text="Signal lost: degrade and log.")
        spec_editor.set_requirement(doc, "VCU-DR-01", text="Torque within 90 milliseconds.")

    revised = parse_spec(_edited(edit))
    return diff_specs(baseline, revised), parse_register(REGISTER, revised, baseline)


def _check(fixture, interpretations, assessments):
    diff, reg = fixture
    raw = LLMImpactResult.model_validate({"change_interpretations": interpretations, "assessments": assessments})
    return post_check(raw, diff, reg)


def _status(checked, test_id):
    return next(a for a in checked.result.assessments if a.test_id == test_id).status


REWORDED = [_interp("VCU-DGN-04", "reworded_same_meaning"), _interp("VCU-DR-01", "tightened")]


def test_rewording_adjustment_is_applied(reworded_and_tightened):
    checked = _check(reworded_and_tightened, REWORDED, [_assessment("TV-005", "directly_affected", ["VCU-DGN-04"])])
    tv005 = next(a for a in checked.result.assessments if a.test_id == "TV-005")
    assert tv005.status == "not_affected"
    assert tv005.reason == "the model's reason"  # only the status is corrected
    assert tv005.confidence == "high"


def test_rewording_adjustment_is_recorded_outside_the_llm_schema(reworded_and_tightened):
    checked = _check(reworded_and_tightened, REWORDED, [_assessment("TV-005", "directly_affected", ["VCU-DGN-04"])])
    [adj] = checked.adjustments
    assert (adj.test_id, adj.rule) == ("TV-005", "rewording_contradiction")
    assert (adj.original_status, adj.new_status) == ("directly_affected", "not_affected")
    assert "VCU-DGN-04" in adj.reason
    assert any("TV-005" in w and "changed from directly_affected to not_affected" in w for w in checked.warnings)
    # The record is run-level information, never part of the schema sent to the model.
    assert "adjustments" not in LLMImpactResult.model_fields and "adjustments" not in models.TestAssessment.model_fields
    assert "adjustments" in AnalysisRun.model_fields


def test_mixed_related_requirements_are_untouched(reworded_and_tightened):
    checked = _check(
        reworded_and_tightened,
        REWORDED,
        [_assessment("TV-001", "directly_affected", ["VCU-DGN-04", "VCU-DR-01"])],
    )
    assert _status(checked, "TV-001") == "directly_affected"
    assert checked.adjustments == [] and not any("TV-001" in w for w in checked.warnings)


def test_empty_related_requirements_are_untouched_and_warn_only_for_pure_rewordings(baseline):
    revised = parse_spec(_edited(lambda d: spec_editor.set_requirement(d, "VCU-DGN-04", text="Signal lost: degrade.")))
    only_rewording = (diff_specs(baseline, revised), parse_register(REGISTER, revised, baseline))
    assessments = [_assessment("TV-005", "directly_affected", [])]
    checked = _check(only_rewording, [_interp("VCU-DGN-04", "reworded_same_meaning")], assessments)
    assert _status(checked, "TV-005") == "directly_affected" and checked.adjustments == []
    assert any("TV-005" in w and "without naming a changed requirement" in w for w in checked.warnings)
    # With a real change in the same run the empty list is not suspicious: no warning.
    other = _check(only_rewording, [_interp("VCU-DGN-04", "tightened")], assessments)
    assert _status(other, "TV-005") == "directly_affected"
    assert not any("without naming" in w for w in other.warnings)


@pytest.mark.parametrize("nature", ["tightened", "relaxed", "scope_changed", "other"])
def test_non_rewording_changes_are_untouched(reworded_and_tightened, nature):
    interpretations = [_interp("VCU-DGN-04", nature), _interp("VCU-DR-01", "tightened")]
    checked = _check(
        reworded_and_tightened, interpretations, [_assessment("TV-005", "directly_affected", ["VCU-DGN-04"])]
    )
    assert _status(checked, "TV-005") == "directly_affected" and checked.adjustments == []


def test_adjustment_only_concerns_directly_affected_tests_with_an_interpretation(reworded_and_tightened):
    checked = _check(
        reworded_and_tightened,
        [_interp("VCU-DGN-04", "reworded_same_meaning")],  # no interpretation for VCU-DR-01
        [
            _assessment("TV-005", "possibly_affected", ["VCU-DGN-04"]),
            _assessment("TV-006", "not_affected", ["VCU-DGN-04"]),
            _assessment("TV-001", "directly_affected", ["VCU-DR-01"]),  # related requirement not interpreted
        ],
    )
    assert _status(checked, "TV-005") == "possibly_affected"
    assert _status(checked, "TV-006") == "not_affected"
    assert _status(checked, "TV-001") == "directly_affected"
    assert checked.adjustments == []


def test_adjusted_status_still_triggers_the_action_consistency_warning(reworded_and_tightened):
    checked = _check(
        reworded_and_tightened,
        REWORDED,
        [_assessment("TV-005", "directly_affected", ["VCU-DGN-04"], actions=("rerun",))],
    )
    assert _status(checked, "TV-005") == "not_affected"
    assert any("TV-005" in w and "status not_affected but actions" in w for w in checked.warnings)


def test_apply_edits_and_validation(baseline):
    from vcu_impact.spec_editor import SpecEdit, apply_edits, validate_new_id

    edits = [
        SpecEdit(op="set", req_id="VCU-DR-01", text="Torque within 90 milliseconds."),
        SpecEdit(op="add", req_id="VCU-THM-07", title="Thermal", text="Derate.", after="VCU-MOD-06"),
        SpecEdit(op="remove", req_id="VCU-LOG-05"),
    ]
    revised = parse_spec(apply_edits(BASELINE.read_bytes(), edits))
    assert revised.requirement("VCU-DR-01").text == "Torque within 90 milliseconds."
    assert revised.requirement_ids[-1] == "VCU-THM-07" and "VCU-LOG-05" not in revised.requirement_ids
    with pytest.raises(ValueError, match="Edit 2"):
        apply_edits(BASELINE.read_bytes(), [edits[2], SpecEdit(op="set", req_id="VCU-LOG-05", text="x")])
    assert validate_new_id("VCU-THM-07", ALL_IDS) is None
    assert "already exists" in validate_new_id("VCU-DR-01", ALL_IDS)
    assert validate_new_id("thermal 7", ALL_IDS)
