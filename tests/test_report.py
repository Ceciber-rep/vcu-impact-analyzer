"""Report content tests (offline)."""

import sys
from pathlib import Path

import pytest

from vcu_impact import cache, spec_editor
from vcu_impact.analysis import approval_language
from vcu_impact.pipeline import InputFile, Inputs, analyze, build_rows, default_inputs, prepare
from vcu_impact.report import build_report, render_html, render_markdown

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "eval"))
from evaluate import load_dataset, scenario_path  # noqa: E402


@pytest.fixture(autouse=True)
def isolated(monkeypatch, tmp_path):
    monkeypatch.delenv("LLM_PROVIDER", raising=False)
    monkeypatch.setattr(cache, "LOCAL_CACHE_DIR", tmp_path / "cache")


def _reports(inputs: Inputs, edits=None) -> tuple[str, str]:
    prep = prepare(inputs)
    out = analyze(prep, mode="replay")
    data = build_report(prep, out, build_rows(prep, out), edits)
    return render_html(data), render_markdown(data)


def test_report_has_required_content():
    html, md = _reports(default_inputs())
    for doc in (html, md):
        assert "Recommendations only" in doc and "final approval belongs to the authorized owner" in doc
        assert "Replayed" in doc and "groq:qwen/qwen3.8-27b" in doc
        assert all(f"TV-{n:03d}" in doc for n in range(1, 13))  # every test, including not affected
        assert "VCU-DR-01" in doc and "Fix requirement link *" in doc
        assert approval_language(doc) == []  # nothing reads as an approval
    assert "<del>100</del><ins>80</ins>" in html
    assert "~~100~~**80**" in md


def test_report_shows_the_status_adjustment():
    sc = next(s for s in load_dataset()["scenarios"] if s["id"] == "S5")
    d = default_inputs()
    html, md = _reports(Inputs(d.baseline, InputFile.from_path(scenario_path(sc)), d.register))
    for doc in (html, md):
        assert "changed from directly_affected to not_affected" in doc  # shown next to TV-005
        assert "post-check, not by the model" in doc


def test_report_without_analysis_and_with_edits():
    doc = spec_editor.load(default_inputs().revised.data)
    spec_editor.replace_in_requirement(doc, "VCU-DR-01", "80", "90")
    d = default_inputs()
    html, md = _reports(
        Inputs(d.baseline, InputFile("x.docx", spec_editor.to_bytes(doc)), d.register), edits=["Edited VCU-DR-01"]
    )
    for text in (html, md):
        assert "Not analysed" in text and "Edited VCU-DR-01" in text and "TV-012" in text


def test_html_escapes_document_text():
    doc = spec_editor.load(default_inputs().revised.data)
    spec_editor.set_requirement(doc, "VCU-DR-02", text="Filter <script>alert(1)</script> spikes.")
    d = default_inputs()
    html, _ = _reports(Inputs(d.baseline, InputFile("x.docx", spec_editor.to_bytes(doc)), d.register))
    assert "<script>alert(1)</script>" not in html and "&lt;script&gt;" in html
