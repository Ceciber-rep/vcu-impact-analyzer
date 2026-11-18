"""Phase 3 robustness tests for specification and register inputs. Offline, deterministic.

Tests that document a known defect are marked ``xfail(strict=True)`` with the finding id
(docs/assessment/03_edge_cases.md): they pass again, loudly, once the defect is fixed.
"""

import sys
import zipfile
from io import BytesIO
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent))
from builders import (  # noqa: E402
    make_register,
    make_spec,
    make_test,
    with_comment_and_header,
    with_table_requirement,
    with_text_box,
    with_tracked_change,
)

from vcu_impact import cache, pipeline  # noqa: E402
from vcu_impact.diff import numeric_changes  # noqa: E402
from vcu_impact.pipeline import InputFile, Inputs, analyze, prepare  # noqa: E402
from vcu_impact.register_parser import parse_register  # noqa: E402
from vcu_impact.spec_parser import parse_spec  # noqa: E402

BASE = make_spec([("VCU-A-01", "Limit", "The value is 100 ms."), ("VCU-B-02", "Other", "Keep 5 V.")])
REG = make_register([make_test(1, link="VCU-A-01"), make_test(2, link="VCU-B-02")])


@pytest.fixture(autouse=True)
def no_model(monkeypatch, tmp_path):
    for var in ("LLM_PROVIDER", "LLM_FALLBACK_PROVIDER"):
        monkeypatch.setenv(var, "")
    monkeypatch.setattr(cache, "LOCAL_CACHE_DIR", tmp_path / "cache")
    monkeypatch.setattr(cache, "REPLAY_DIR", tmp_path / "replay")


def _prep(baseline=BASE, revised=BASE, register=REG):
    return prepare(Inputs(InputFile("b.docx", baseline), InputFile("r.docx", revised), InputFile("t.xlsx", register)))


# ---- specification pairs -------------------------------------------------------------------------


def test_identical_specs_give_no_changes_and_a_clear_state():  # E-001
    prep = _prep()
    assert not prep.diff.has_requirement_changes
    out = analyze(prep, mode="live")
    assert out.mode == "not_analysed" and "nothing to assess" in out.reason


def test_same_file_uploaded_twice_is_identical():  # E-002
    assert not _prep(BASE, BASE).diff.has_requirement_changes


def test_swapped_baseline_and_revised_invert_the_change():  # E-003
    new = make_spec([("VCU-A-01", "Limit", "The value is 80 ms."), ("VCU-B-02", "Other", "Keep 5 V.")])
    fwd, back = _prep(BASE, new).diff, _prep(new, BASE).diff
    f, b = fwd.requirement_changes[0], back.requirement_changes[0]
    assert (f.numeric_changes[0].old_value, f.numeric_changes[0].new_value) == (100, 80)
    assert (b.numeric_changes[0].old_value, b.numeric_changes[0].new_value) == (80, 100)


def test_added_removed_and_renamed_ids():  # E-004
    new = make_spec([("VCU-A-01", "Limit", "The value is 100 ms."), ("VCU-C-03", "Other", "Keep 5 V.")])
    kinds = {c.req_id: c.change_type.value for c in _prep(BASE, new).diff.requirement_changes}
    assert kinds == {"VCU-C-03": "added", "VCU-B-02": "removed"}  # a rename is an add plus a remove, by design


def test_duplicate_requirement_ids_are_rejected_with_the_id_named():  # E-005
    dup = make_spec([("VCU-A-01", "x", "a 1 ms"), ("VCU-A-01", "y", "b 2 ms")])
    with pytest.raises(ValueError, match="Duplicate requirement ID.*VCU-A-01"):
        parse_spec(dup)


def test_requirement_without_body_parses_and_diffs():  # E-006
    empty = make_spec([("VCU-A-01", "Limit", "")])
    assert parse_spec(empty).requirements[0].text == ""
    assert _prep(BASE, empty).diff.requirement_changes[0].change_type.value == "modified"


def test_very_long_requirement_is_handled_and_prompt_size_is_known():  # E-007
    long = make_spec([("VCU-A-01", "Limit", "The value is 100 ms. " + "Word " * 60_000)])
    prep = _prep(BASE, long)
    assert len(prep.user_prompt) > 300_000  # no truncation and no guard: the provider will reject it
    assert prep.diff.requirement_changes


@pytest.mark.parametrize("ident", ["SYS_001", "vcu-a-01", "VCU-A-01a", "R1"])
@pytest.mark.xfail(strict=True, reason="F-012: unrecognised heading is silently merged into the previous requirement")
def test_unrecognised_id_format_is_not_swallowed_silently(ident):  # E-008
    spec = make_spec([("VCU-A-01", "Limit", "The value is 100 ms."), (ident, "Next", "Another 5 ms.")])
    parsed = parse_spec(spec)
    swallowed = "Another 5 ms." in parsed.requirements[0].text and len(parsed.requirements) == 1
    assert not swallowed  # either it is recognised or the user is told; today it is neither


@pytest.mark.xfail(strict=True, reason="F-012: 'VCU-A-01.2' is read as ID VCU-A-01 with title '2 ...'")
def test_id_followed_by_dot_number_is_not_truncated():  # E-009
    assert parse_spec(make_spec([("VCU-A-01.2", "T", "x 1 ms")])).requirements[0].req_id != "VCU-A-01"


# ---- numbers and units -----------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("old", "new"),
    [("within 100 ms", "within 100 milliseconds"), ("1,5 s", "1.5 s"), ("5 %", "5 percent")],
)
def test_equal_numbers_in_equivalent_spellings_are_not_changes(old, new):  # E-010
    assert numeric_changes(old, new) == []


@pytest.mark.parametrize(("old", "new"), [("within 100 ms", "within 0.1 s"), ("within 100 ms", "within 0.10 seconds")])
@pytest.mark.xfail(strict=True, reason="F-001: units are not converted, 100 ms vs 0.1 s is reported as a change")
def test_equal_numbers_in_different_units_are_not_changes(old, new):  # E-011
    assert numeric_changes(old, new) == []


def test_changed_percentage_and_range_are_reported():  # E-012
    assert [(c.old_value, c.new_value) for c in numeric_changes("above 70%", "above 90%")] == [(70, 90)]
    assert [(c.old_value, c.new_value) for c in numeric_changes("between 10 and 20 ms", "between 10 and 30 ms")] == [
        (20, 30)
    ]


@pytest.mark.xfail(strict=True, reason="F-001: a number inside a referenced ID is reported as a numeric change")
def test_numbers_inside_ids_are_not_numeric_changes():  # E-013
    assert numeric_changes("see VCU-DR-01 within 80 ms", "see VCU-DR-02 within 80 ms") == []


# ---- Word documents --------------------------------------------------------------------------------
    strict=True, reason="F-010: text inside tracked changes (w:ins / w:del) is ignored without a warning"
)
def test_tracked_change_in_a_requirement_is_seen():  # E-014
    tracked = with_tracked_change(BASE, "VCU-A-01", "100 ms", "80 ms")
    text = parse_spec(tracked).requirements[0].text
    assert "80 ms" in text and "100 ms" not in text  # read as if accepted: insertion kept, deletion dropped


def test_tracked_change_does_not_hide_the_change_from_the_diff():  # E-015
    tracked = with_tracked_change(BASE, "VCU-A-01", "100 ms", "80 ms")
    change = _prep(BASE, tracked).diff.requirement_changes[0]
    assert "80 ms" in change.new.text and change.numeric_changes[0].new_value == 80
    assert any("tracked changes" in w for w in _prep(BASE, tracked).input_warnings)  # and the user is told


@pytest.mark.xfail(strict=True, reason="F-011: requirements in text boxes or in tables are ignored without a warning")
@pytest.mark.parametrize("variant", ["textbox", "table"])
def test_requirement_outside_normal_paragraphs_is_not_lost_silently(variant):  # E-016
    doc = (
        with_text_box(BASE, "VCU-TXT-09  Boxed")
        if variant == "textbox"
        else with_table_requirement(BASE, ("VCU-TAB-02", "x 5 ms"))
    )
    ids = [r.req_id for r in parse_spec(doc).requirements]
    assert len(ids) == 3  # today only the 2 normal requirements are found, no warning anywhere


def test_header_text_and_non_requirement_sections():  # E-017
    other = make_spec(
        [("VCU-A-01", "Limit", "The value is 100 ms."), ("VCU-B-02", "Other", "Keep 5 V.")],
        sections={"Assumptions": "The bench uses clock X."},
    )
    changed = make_spec(
        [("VCU-A-01", "Limit", "The value is 100 ms."), ("VCU-B-02", "Other", "Keep 5 V.")],
        sections={"Assumptions": "The bench uses clock Y."},
    )
    diff = _prep(other, changed).diff
    assert not diff.has_requirement_changes and [s.name for s in diff.section_changes] == ["Assumptions"]
    assert analyze(_prep(other, changed), mode="live").mode == "not_analysed"  # the LLM never sees section-only changes
    assert [r.req_id for r in parse_spec(with_comment_and_header(BASE, "VCU-HDR-03 x")).requirements] == [
        "VCU-A-01",
        "VCU-B-02",
    ]


def _is_clear(exc: Exception) -> bool:
    return isinstance(exc, ValueError) and any(
        w in str(exc).lower() for w in ("word", "excel", "docx", "xlsx", "valid")
    )


@pytest.mark.parametrize("name", ["empty", "garbage", "ole_doc_or_encrypted"])
@pytest.mark.xfail(strict=True, reason="F-013: corrupt/empty/old-format/encrypted uploads give raw library errors")
def test_bad_spec_files_give_a_clear_error(name):  # E-018
    data = {
        "empty": b"",
        "garbage": b"hello",
        "ole_doc_or_encrypted": bytes.fromhex("D0CF11E0A1B11AE1") + b"\0" * 600,
    }[name]
    with pytest.raises(Exception) as ei:  # noqa: PT011
        parse_spec(data, "x.docx")
    assert _is_clear(ei.value), f"{type(ei.value).__name__}: {ei.value}"


def test_xlsx_uploaded_as_spec_says_it_is_not_a_word_file():  # E-018b
    with pytest.raises(ValueError, match="not a Word file"):
        parse_spec(REG, "x.docx")


@pytest.mark.parametrize("name", ["empty", "garbage", "docx_as_xlsx"])
@pytest.mark.xfail(strict=True, reason="F-013: corrupt/empty/wrong-type uploads give raw library errors")
def test_bad_register_files_give_a_clear_error(name):  # E-019
    data = {"empty": b"", "garbage": b"hello", "docx_as_xlsx": BASE}[name]
    with pytest.raises(Exception) as ei:  # noqa: PT011
        parse_register(data, None, None, "x.xlsx")
    assert _is_clear(ei.value), f"{type(ei.value).__name__}: {ei.value}"


def test_large_spec_file_parses():  # E-020
    big = make_spec([(f"VCU-X-{i:03d}", f"R{i}", f"The value is {i} ms. " + "text " * 40) for i in range(1, 400)])
    assert len(big) > 20_000 and len(parse_spec(big).requirements) == 399


# ---- register files ----------------------------------------------------------------------------------


def _reg(rows, **kw):
    sp = parse_spec(BASE)
    return parse_register(make_register(rows, **kw), sp, sp)


def test_register_with_zero_tests_is_rejected_clearly():  # E-021
    with pytest.raises(ValueError, match="No test table found"):
        _reg([])


def test_register_with_one_test_and_blank_rows():  # E-022
    reg = _reg([[None] * 8, make_test(1), [], make_test(2)])
    assert [t.test_id for t in reg.tests] == ["TV-001", "TV-002"]


def test_register_with_other_column_order_and_header_wording():  # E-023
    reg = _reg(
        [["ECU test", "TV-001", "VCU-A-01", "PASS (9 ms)"]],
        headers=["Test name", "Test case", "Req reference", "Result"],
    )
    assert reg.tests[0].test_id == "TV-001" and reg.tests[0].links[0].status.value == "valid"
    reg = _reg([["TV-001", "n", "VCU-A-01", "PASS"]], headers=["ID", "Title", "Trace", "Verdict"])
    assert reg.tests[0].links[0].status.value == "valid"


def test_register_with_extra_columns():  # E-024
    assert (
        len(_reg([make_test(1) + ["x", "y"]], headers=[*make_register.__globals__["HEADERS"], "E1", "E2"]).tests) == 1
    )


@pytest.mark.xfail(
    strict=True, reason="F-014: text in merged cells and formulas without cached values is dropped silently"
)
def test_merged_cells_and_uncached_formulas_are_not_dropped_silently():  # E-025
    def messy(wb, ws):
        ws.merge_cells("B4:C4")
        ws["E4"] = '="PASS"&" (90 ms)"'

    reg = _reg([make_test(1)], extra=messy)
    t = reg.tests[0]
    assert t.procedure and t.result_raw  # today both are empty strings and nothing says so


@pytest.mark.xfail(strict=True, reason="F-015: duplicate test IDs are accepted silently")
def test_duplicate_test_ids_are_flagged():  # E-026
    with pytest.raises(ValueError, match="TV-001"):
        _reg([make_test(1), make_test(1)])


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("VCU-A-01; VCU-B-02", ["VCU-A-01", "VCU-B-02"]),
        ("VCU-A-01, VCU-B-02", ["VCU-A-01", "VCU-B-02"]),
        ("VCU-A-01 (see note)", ["VCU-A-01"]),
        ("N/A", [None]),
        ("see notes", [None]),
    ],
)
def test_link_cells_in_common_formats(raw, expected):  # E-027
    reg = _reg([make_test(1, link=raw)])
    assert [link.req_id for link in reg.tests[0].links] == expected


@pytest.mark.parametrize("raw", ["VCU-A-01\nVCU-B-02", "VCU-A-01 VCU-B-02", "VCU-A-01 and VCU-B-02"])
@pytest.mark.xfail(strict=True, reason="F-016: only the first ID is kept when IDs are separated by a newline or space")
def test_link_cell_with_several_ids_keeps_all_of_them(raw):  # E-028
    reg = _reg([make_test(1, link=raw)])
    assert [link.req_id for link in reg.tests[0].links] == ["VCU-A-01", "VCU-B-02"]


@pytest.mark.xfail(strict=True, reason="F-017: a lower-case ID is reported as an unknown requirement")
def test_lowercase_id_in_link_cell_is_matched():  # E-029
    assert _reg([make_test(1, link="vcu-a-01")]).tests[0].links[0].status.value == "valid"


def test_register_with_200_tests_builds_a_prompt_and_reports_its_size():  # E-030
    reg = make_register([make_test(i, link="VCU-A-01") for i in range(1, 201)])
    new = make_spec([("VCU-A-01", "Limit", "The value is 80 ms."), ("VCU-B-02", "Other", "Keep 5 V.")])
    prep = _prep(BASE, new, reg)
    assert len(prep.register.tests) == 200
    # about 4.3 k prompt tokens for 12 tests: 200 tests need roughly 70 k and output of 200 assessments about 30 k
    assert len(prep.user_prompt) > 90_000


def test_zip_without_content_is_not_a_crash_in_the_app_path():  # E-031
    buf = BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("hello.txt", "x")
    with pytest.raises(Exception):  # noqa: B017, PT011  (documented under F-013)
        parse_spec(buf.getvalue(), "x.docx")


def test_pipeline_is_deterministic_for_identical_input():  # E-032
    new = make_spec([("VCU-A-01", "Limit", "The value is 80 ms."), ("VCU-B-02", "Other", "Keep 5 V.")])
    assert _prep(BASE, new).key == _prep(BASE, new).key
    assert pipeline.analyze(_prep(BASE, new), mode="replay").mode == "not_analysed"
