"""VCU-42 change impact analyzer: Streamlit UI.

uv run streamlit run app/streamlit_app.py
"""

from __future__ import annotations

import sys
from pathlib import Path

import streamlit as st
from dotenv import load_dotenv

sys.path.insert(0, str(Path(__file__).resolve().parent))
import components as ui  # noqa: E402

from vcu_impact.pipeline import (  # noqa: E402
    REPO,
    AnalysisOutcome,
    InputFile,
    Inputs,
    Prepared,
    analyze,
    build_rows,
    configured_llms,
    default_inputs,
    prepare,
)
from vcu_impact.register_parser import parse_register  # noqa: E402
from vcu_impact.report import build_report, render_html, render_markdown  # noqa: E402
from vcu_impact.spec_editor import SpecEdit, apply_edits, validate_new_id  # noqa: E402
from vcu_impact.spec_parser import parse_spec  # noqa: E402

load_dotenv(REPO / ".env")
st.set_page_config(page_title="VCU-42 change impact", page_icon="🔧", layout="wide")
ui.inject_css()


# ---------------------------------------------------------------------------
# State: base files (provided or uploaded) + an ordered list of edits applied to
# the revised spec. Everything else is derived and cached.
# ---------------------------------------------------------------------------


def _state() -> None:
    ss = st.session_state
    if "base" not in ss:
        ss.base = default_inputs()
    ss.setdefault("edits", [])  # list[SpecEdit] applied to base.revised
    ss.setdefault("live_outcomes", {})  # cache key -> AnalysisOutcome from this session
    ss.setdefault("notice", None)


@st.cache_data(show_spinner=False)
def _edited(data: bytes, edits_json: tuple[str, ...]) -> bytes:
    return apply_edits(data, [SpecEdit.model_validate_json(e) for e in edits_json])


@st.cache_data(show_spinner=False)
def _prepare(b: tuple[str, bytes], r: tuple[str, bytes], g: tuple[str, bytes]) -> Prepared:
    return prepare(Inputs(InputFile(*b), InputFile(*r), InputFile(*g)))


@st.cache_data(show_spinner=False)
def _replay(key: str, _prep: Prepared) -> AnalysisOutcome:
    return analyze(_prep, mode="replay")


def _effective_inputs() -> Inputs:
    base: Inputs = st.session_state.base
    edits: list[SpecEdit] = st.session_state.edits
    if not edits:
        return base
    data = _edited(base.revised.data, tuple(e.model_dump_json() for e in edits))
    name = Path(base.revised.name).stem + "_edited.docx"
    return Inputs(base.baseline, InputFile(name, data), base.register)


def _current() -> Prepared:
    i = _effective_inputs()
    return _prepare(
        (i.baseline.name, i.baseline.data), (i.revised.name, i.revised.data), (i.register.name, i.register.data)
    )


def _outcome(prep: Prepared) -> AnalysisOutcome:
    return st.session_state.live_outcomes.get(prep.key) or _replay(prep.key, prep)


# ---------------------------------------------------------------------------
# Sidebar: inputs and analysis
# ---------------------------------------------------------------------------


def _on_upload(kind: str) -> None:
    """Validate an uploaded file by parsing it before it replaces anything."""
    file = st.session_state.get(f"up_{kind}")
    if file is None:
        return
    new = InputFile(file.name, file.getvalue())
    base: Inputs = st.session_state.base
    try:
        if kind == "register":
            parse_register(new.data, source_name=new.name)
        else:
            spec = parse_spec(new.data, new.name)
            if not spec.requirements:
                raise ValueError("no requirement found (expected paragraphs starting with an ID like VCU-DR-01)")
    except Exception as exc:  # noqa: BLE001 - any parse failure is reported to the user
        st.session_state.notice = ("error", f"{new.name} was not loaded: {exc}")
        return
    fields = {"baseline": base.baseline, "revised": base.revised, "register": base.register} | {kind: new}
    st.session_state.base = Inputs(**fields)
    if kind == "revised":
        st.session_state.edits = []  # edits were made on the previous revised file
    st.session_state.notice = ("success", f"Loaded {new.name} as the {kind} file.")


def _restore_defaults() -> None:
    st.session_state.base = default_inputs()
    st.session_state.edits = []
    st.session_state.notice = ("success", "Restored the provided files.")


def sidebar_inputs() -> None:
    sb = st.sidebar
    sb.title("VCU-42 change impact")
    sb.caption("Compare two specification revisions and assess the existing tests.")
    with sb.expander("Use other files", expanded=False):
        for kind, label, ext in (
            ("baseline", "Baseline spec (.docx)", "docx"),
            ("revised", "Revised spec (.docx)", "docx"),
            ("register", "Test register (.xlsx)", "xlsx"),
        ):
            st.file_uploader(label, type=[ext], key=f"up_{kind}", on_change=_on_upload, args=(kind,))
        st.button("Restore the provided files", on_click=_restore_defaults, width="stretch")


def sidebar_summary(prep: Prepared, outcome: AnalysisOutcome) -> None:
    sb = st.sidebar
    i = prep.inputs
    edits = st.session_state.edits
    sb.subheader("Inputs")
    sb.markdown(
        f"- **Baseline:** {i.baseline.name}  \n  {prep.baseline.revision}\n"
        f"- **Revised:** {i.revised.name}  \n  {prep.revised.revision}"
        + (f"  \n  _{len(edits)} edit(s) applied in the app_" if edits else "")
        + f"\n- **Register:** {i.register.name}  \n  {len(prep.register.tests)} tests, "
        f"{len(prep.register.notes)} notes"
    )
    if len(prep.register.tests) > 60:
        sb.warning("Large register: the analysis was evaluated with 12 tests; above ~60 tests it is untested.")

    sb.subheader("Analysis")
    configs, problems = configured_llms()
    if configs:
        sb.markdown(
            "Model: **" + configs[0].label + "**" + (f"  \nFallback: {configs[1].label}" if len(configs) > 1 else "")
        )
    for p in problems:
        sb.caption(p)
    can_run = bool(configs) and prep.diff.has_requirement_changes
    label = "Re-run analysis with the LLM" if outcome.run else "Run analysis with the LLM"
    if sb.button(label, type="primary", disabled=not can_run, width="stretch"):
        with st.spinner(f"Calling {configs[0].label}… this takes a few seconds to a few minutes."):
            st.session_state.live_outcomes[prep.key] = analyze(prep, mode="live")
        st.rerun()
    if not configs:
        sb.caption("Without a model, recorded analyses (replay) are shown when they exist for the inputs.")
    sb.caption(f"Input key `{prep.key[:12]}` · prompt {outcome.run.prompt_version if outcome.run else '—'}")


# ---------------------------------------------------------------------------
# Edit tab
# ---------------------------------------------------------------------------


def _add_edit(edit: SpecEdit) -> None:
    edits = [*st.session_state.edits, edit]
    try:
        _edited(st.session_state.base.revised.data, tuple(e.model_dump_json() for e in edits))
    except ValueError as exc:
        st.session_state.notice = ("error", str(exc))
        return
    st.session_state.edits = edits
    st.session_state.notice = (
        "success",
        f"{edit.describe()}. The diff in tab 1 is updated; run the analysis to update the assessment.",
    )


def edit_tab(prep: Prepared) -> None:
    st.markdown(
        "Edits are applied to the revised specification (the .docx itself), then parsed again exactly like an "
        "uploaded file. The diff updates immediately; the LLM assessment is updated when you run the analysis."
    )
    ids = prep.revised.requirement_ids
    mode = st.radio(
        "Change", ["Edit a requirement", "Add a requirement", "Remove a requirement"], horizontal=True, key="edit_mode"
    )

    if mode == "Edit a requirement":
        req_id = st.selectbox("Requirement", ids, key="edit_req")
        req = prep.revised.requirement(req_id)
        with st.form(f"form_edit_{req_id}"):
            title = st.text_input("Title", value=req.title)
            text = st.text_area("Requirement text", value=req.text, height=140)
            if st.form_submit_button("Apply edit", type="primary"):
                if text.strip() == req.text and title.strip() == req.title:
                    st.session_state.notice = ("info", "Nothing changed.")
                else:
                    _add_edit(SpecEdit(op="set", req_id=req_id, title=title.strip(), text=text.strip()))
                st.rerun()

    elif mode == "Add a requirement":
        with st.form("form_add"):
            c1, c2 = st.columns([1, 2])
            new_id = c1.text_input("New ID", placeholder="VCU-THM-07")
            title = c2.text_input("Title", placeholder="Thermal torque derating")
            text = st.text_area(
                "Requirement text", height=120, placeholder="Under elevated thermal load, the controller shall …"
            )
            after = st.selectbox("Insert after", ids, index=len(ids) - 1)
            if st.form_submit_button("Add requirement", type="primary"):
                error = validate_new_id(new_id.strip(), ids) or ("" if text.strip() else "Enter the text.")
                if error:
                    st.session_state.notice = ("error", error)
                else:
                    edit = SpecEdit(
                        op="add", req_id=new_id.strip(), title=title.strip(), text=text.strip(), after=after
                    )
                    _add_edit(edit)
                st.rerun()

    else:
        with st.form("form_remove"):
            req_id = st.selectbox("Requirement to remove", ids)
            if st.form_submit_button("Remove requirement", type="primary"):
                if len(ids) == 1:
                    st.session_state.notice = ("error", "The specification must keep at least one requirement.")
                else:
                    _add_edit(SpecEdit(op="remove", req_id=req_id))
                st.rerun()

    edits: list[SpecEdit] = st.session_state.edits
    st.subheader(f"Applied edits ({len(edits)})")
    if not edits:
        st.caption("None. The revised specification is the file shown in the sidebar.")
        return
    for n, e in enumerate(edits, 1):
        st.markdown(f"{n}. {e.describe()}")
    c1, c2, c3 = st.columns(3)
    if c1.button("Undo last edit", width="stretch"):
        st.session_state.edits = edits[:-1]
        st.rerun()
    if c2.button("Reset all edits", width="stretch"):
        st.session_state.edits = []
        st.rerun()
    c3.download_button(
        "Download edited .docx",
        data=prep.inputs.revised.data,
        file_name=prep.inputs.revised.name,
        mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        width="stretch",
    )


# ---------------------------------------------------------------------------
# Report tab
# ---------------------------------------------------------------------------


def report_tab(prep: Prepared, outcome: AnalysisOutcome, rows) -> None:
    data = build_report(prep, outcome, rows, [e.describe() for e in st.session_state.edits])
    html_doc, md_doc = render_html(data), render_markdown(data)
    stem = Path(prep.inputs.revised.name).stem
    st.markdown(
        "The report contains the inputs and their hashes, the source of the assessment (live or replayed), the "
        "changes, the work list and every test with its reason. HTML prints cleanly to PDF from the browser."
    )
    c1, c2 = st.columns(2)
    c1.download_button(
        "Download HTML report",
        html_doc,
        file_name=f"impact_report_{stem}.html",
        mime="text/html",
        type="primary",
        width="stretch",
    )
    c2.download_button(
        "Download Markdown report", md_doc, file_name=f"impact_report_{stem}.md", mime="text/markdown", width="stretch"
    )
    if outcome.mode == "not_analysed":
        st.warning("No LLM assessment for these inputs: the report will contain the changes and register facts only.")
    # st.iframe runs the HTML with scripts enabled, and the report contains text from uploaded files
    # and from the LLM. This is safe only because the template escapes all of it
    # (tests/test_report.py::test_html_escapes_document_text guards this).
    st.iframe(html_doc, height=900)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def _show_notice() -> None:
    notice = st.session_state.notice
    if notice:
        kind, text = notice
        {"error": st.error, "success": st.success, "info": st.info}[kind](text)
        st.session_state.notice = None


def main() -> None:
    _state()
    sidebar_inputs()
    try:
        prep = _current()
    except ValueError as exc:
        st.error(f"Cannot use the current inputs: {exc}")
        st.button("Restore the provided files", on_click=_restore_defaults)
        st.stop()
    outcome = _outcome(prep)
    sidebar_summary(prep, outcome)

    st.title("Specification change impact")
    _show_notice()
    ui.provenance_banner(outcome)
    st.caption(
        "The register is treated as evidence, not approval. Results are recommendations for engineering review; "
        "final approval belongs to the authorized owner."
    )

    rows = build_rows(prep, outcome)
    tab_changes, tab_impact, tab_edit, tab_report = st.tabs(
        ["1 · What changed", "2 · Affected tests", "3 · Edit and re-analyse", "4 · Report"]
    )
    with tab_changes:
        ui.changes_tab(prep.diff, outcome)
    with tab_impact:
        if outcome.run:
            ui.impact_summary(rows)
        selected = ui.impact_table(rows)
        if selected is None and rows:
            st.caption("No row selected: showing the first test that needs attention.")
            selected = next((r for r in rows if r.assessment and r.assessment.status != "not_affected"), rows[0])
        if selected:
            ui.detail_panel(selected)
    with tab_edit:
        edit_tab(prep)
    with tab_report:
        report_tab(prep, outcome, rows)


main()
