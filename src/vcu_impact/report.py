"""Engineering impact report (HTML and Markdown), built from the same rows as the UI."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape
from pydantic import BaseModel

from vcu_impact.diff import is_rewrite, word_diff
from vcu_impact.models import ImpactStatus, RequiredAction
from vcu_impact.pipeline import AnalysisOutcome, Prepared, TestImpactRow

TEMPLATES = Path(__file__).resolve().parent / "templates"

STATUS_TEXT = {
    ImpactStatus.DIRECTLY_AFFECTED: "Directly affected",
    ImpactStatus.POSSIBLY_AFFECTED: "Possibly affected",
    ImpactStatus.NEEDS_HUMAN_REVIEW: "Needs human review",
    ImpactStatus.NOT_AFFECTED: "Not affected",
}
ACTION_TEXT = {
    RequiredAction.RERUN: "Re-run test",
    RequiredAction.UPDATE_PROCEDURE: "Update procedure",
    RequiredAction.FIX_LINK: "Fix requirement link",
    RequiredAction.OWNER_DECISION: "Owner decision",
    RequiredAction.NONE: "None",
}
_ORDER = list(ImpactStatus)

DISCLAIMER = (
    "This report gives recommendations for engineering review. The test register is treated as evidence "
    "from earlier campaigns, not as approval. Nothing in this report approves a requirement, a test or a "
    "result: final approval belongs to the authorized owner."
)
LIMITATIONS = [
    "Statuses, reasons and model-set actions are LLM judgments and can be wrong; check them before acting.",
    "'Fix requirement link' is set by the application from the register links, not by the model.",
    "The model can mark a test 'directly affected' although it read the change as a rewording with the same "
    "meaning. The application then changes the status to 'not affected' and says so next to the test (a "
    "safety net, not a better model, and never applied when the diff found a changed number); it relies on "
    "the model's reading of the change, which is not evaluated (docs/known_issues.md, issue 1).",
    "The confidence given for each test is the model's own estimate. In the evaluation it did not separate right from "
    "wrong answers (high confidence was wrong about as often as medium), so rely on the reason and the evidence.",
    "The analysis was evaluated on 7 change scenarios of this register (84 judgments); see docs/llm_evaluation.md.",
]


class ReportTest(BaseModel):
    test_id: str
    name: str
    status: str  # text, or "Not analysed"
    status_key: str  # css class
    confidence: str
    actions: list[str]  # code-set actions end with " *"
    reason: str
    recommended_action: str
    evidence: list[str]
    link: str
    previous_result: str
    warnings: list[str]


class ReportChange(BaseModel):
    req_id: str
    title: str
    change_type: str
    segments: list[tuple[str, str]]  # (op, text) word diff
    rewrite: bool = False  # mostly rewritten: show old and new as separate blocks
    old_text: str = ""
    new_text: str = ""
    numeric: list[str]
    interpretation: str


class ReportData(BaseModel):
    generated_at: str
    system: str
    inputs: list[tuple[str, str, str, str]]  # role, name, revision, short hash
    edits: list[str]
    source: str
    mode: str
    model: str
    prompt_version: str
    disclaimer: str
    changes: list[ReportChange]
    other_changes: list[ReportChange]
    unchanged: list[str]
    status_counts: list[tuple[str, int]]
    work_list: list[tuple[str, list[str]]]  # action, "TV-001 Name" items
    tests: list[ReportTest]
    global_warnings: list[str]
    limitations: list[str]


def _diff_fields(old: str, new: str) -> dict:
    segments = word_diff(old, new)
    return {
        "segments": segments,
        "rewrite": bool(old and new) and is_rewrite(segments),
        "old_text": old,
        "new_text": new,
    }


def build_report(
    prep: Prepared, outcome: AnalysisOutcome, rows: list[TestImpactRow], edits: list[str] | None = None
) -> ReportData:
    i = prep.inputs
    run = outcome.run
    interp = {c.requirement_id: c for c in run.result.change_interpretations} if run else {}

    changes = []
    for c in prep.diff.requirement_changes:
        req = c.new or c.old
        it = interp.get(c.req_id)
        changes.append(
            ReportChange(
                req_id=c.req_id,
                title=req.title,
                change_type=c.change_type.value,
                **_diff_fields(c.old.text if c.old else "", c.new.text if c.new else ""),
                numeric=[f"{n.old_text or '—'} → {n.new_text or '—'}" for n in c.numeric_changes if n.unit and c.old],
                interpretation=f"{it.nature.value.replace('_', ' ')}: {it.engineering_summary}" if it else "",
            )
        )
    other = [
        ReportChange(
            req_id="",
            title=s.name,
            change_type="modified",
            **_diff_fields(s.old_text or "", s.new_text or ""),
            numeric=[],
            interpretation="",
        )
        for s in prep.diff.section_changes
    ]

    tests = []
    for r in sorted(rows, key=lambda r: (_ORDER.index(r.assessment.status) if r.assessment else 9, r.test.test_id)):
        a = r.assessment
        tests.append(
            ReportTest(
                test_id=r.test.test_id,
                name=r.test.name,
                status=STATUS_TEXT[a.status] if a else "Not analysed",
                status_key=a.status.value if a else "not_analysed",
                confidence=a.confidence.value if a else "",
                actions=[ACTION_TEXT[x] + (" *" if x in r.actions_from_code else "") for x in a.required_actions]
                if a
                else [],
                reason=a.reason if a else "",
                recommended_action=a.recommended_action if a else "",
                evidence=a.evidence if a else [],
                link="; ".join(
                    f"{link.req_id or link.raw or '(empty)'} ({link.status.value})" for link in r.test.links
                ),
                previous_result=r.test.result_raw,
                warnings=r.warnings,
            )
        )

    analysed = [r for r in rows if r.assessment]
    status_counts = [(STATUS_TEXT[s], sum(r.assessment.status == s for r in analysed)) for s in ImpactStatus]
    work_list = []
    for action in (
        RequiredAction.RERUN,
        RequiredAction.UPDATE_PROCEDURE,
        RequiredAction.FIX_LINK,
        RequiredAction.OWNER_DECISION,
    ):
        items = [f"{r.test.test_id} {r.test.name}" for r in analysed if action in r.assessment.required_actions]
        work_list.append((ACTION_TEXT[action], items))

    test_ids = {t.test_id for t in prep.register.tests}
    all_warnings = (run.warnings if run else []) + outcome.warnings
    global_warnings = [*prep.input_warnings, *[w for w in all_warnings if not any(t in w for t in test_ids)]]

    return ReportData(
        generated_at=datetime.now(UTC).strftime("%Y-%m-%d %H:%M UTC"),
        system=prep.revised.title or "Specification",
        inputs=[
            ("Baseline specification", i.baseline.name, prep.baseline.revision, i.baseline.sha256[:12]),
            ("Revised specification", i.revised.name, prep.revised.revision, i.revised.sha256[:12]),
            ("Test register", i.register.name, f"{len(prep.register.tests)} tests", i.register.sha256[:12]),
        ],
        edits=edits or [],
        source=outcome.source_text,
        mode=outcome.mode,
        model=outcome.model_label,
        prompt_version=run.prompt_version if run else "",
        disclaimer=DISCLAIMER,
        changes=changes,
        other_changes=other,
        unchanged=prep.diff.unchanged_requirement_ids,
        status_counts=status_counts,
        work_list=work_list,
        tests=tests,
        global_warnings=global_warnings,
        limitations=LIMITATIONS,
    )


def _md_cell(text: str) -> str:
    """Make text safe inside a Markdown table cell."""
    return str(text).replace("|", "\\|").replace("\n", " ")


def _md_diff(segments: list[tuple[str, str]]) -> str:
    out = []
    for op, text in segments:
        if op == "equal" or not text.strip():
            out.append(text)
        else:
            lead, core, trail = text[: len(text) - len(text.lstrip())], text.strip(), text[len(text.rstrip()) :]
            mark = "~~" if op == "delete" else "**"
            out.append(f"{lead}{mark}{core}{mark}{trail}")
    return "".join(out).replace("\n", " ")


def _env() -> Environment:
    env = Environment(
        loader=FileSystemLoader(TEMPLATES),
        autoescape=select_autoescape(enabled_extensions=("html.j2",), default_for_string=False),  # escape HTML only
        trim_blocks=True,
        lstrip_blocks=True,
    )
    env.filters["cell"] = _md_cell
    env.filters["mddiff"] = _md_diff
    return env


def render_html(data: ReportData) -> str:
    return _env().get_template("report.html.j2").render(r=data)


def render_markdown(data: ReportData) -> str:
    return _env().get_template("report.md.j2").render(r=data)
