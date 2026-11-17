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

load_dotenv(REPO / ".env")
st.set_page_config(page_title="VCU-42 change impact", page_icon="🔧", layout="wide")
ui.inject_css()


# ---------------------------------------------------------------------------
# State
# ---------------------------------------------------------------------------


def _state() -> None:
    ss = st.session_state
    ss.setdefault("inputs", default_inputs())
    ss.setdefault("live_outcomes", {})  # cache key -> AnalysisOutcome produced in this session


@st.cache_data(show_spinner=False)
def _prepare(b: tuple[str, bytes], r: tuple[str, bytes], g: tuple[str, bytes]) -> Prepared:
    return prepare(Inputs(InputFile(*b), InputFile(*r), InputFile(*g)))


@st.cache_data(show_spinner=False)
def _replay(key: str, _prep: Prepared) -> AnalysisOutcome:
    return analyze(_prep, mode="replay")


def _current() -> Prepared:
    i: Inputs = st.session_state.inputs
    return _prepare(
        (i.baseline.name, i.baseline.data), (i.revised.name, i.revised.data), (i.register.name, i.register.data)
    )


def _outcome(prep: Prepared) -> AnalysisOutcome:
    live = st.session_state.live_outcomes.get(prep.key)
    return live or _replay(prep.key, prep)


# ---------------------------------------------------------------------------
# Sidebar
# ---------------------------------------------------------------------------


def sidebar(prep: Prepared, outcome: AnalysisOutcome) -> None:
    sb = st.sidebar
    sb.title("VCU-42 change impact")
    sb.caption("Compare two specification revisions and assess the existing tests.")

    sb.subheader("Inputs")
    i = prep.inputs
    sb.markdown(
        f"- **Baseline:** {i.baseline.name}  \n  {prep.baseline.revision}\n"
        f"- **Revised:** {i.revised.name}  \n  {prep.revised.revision}\n"
        f"- **Register:** {i.register.name}  \n  {len(prep.register.tests)} tests, {len(prep.register.notes)} notes"
    )

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
        with st.spinner(f"Calling {configs[0].label}… this can take from a few seconds to a few minutes."):
            st.session_state.live_outcomes[prep.key] = analyze(prep, mode="live")
        st.rerun()
    if not configs:
        sb.caption("Without a model the app shows recorded analyses (replay) when they exist for the inputs.")
    sb.caption(f"Input key `{prep.key[:12]}` · prompt {outcome.run.prompt_version if outcome.run else '—'}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> None:
    _state()
    try:
        prep = _current()
    except ValueError as exc:
        st.error(f"Cannot read the input files: {exc}")
        st.stop()
    outcome = _outcome(prep)
    sidebar(prep, outcome)

    st.title("Specification change impact")
    ui.provenance_banner(outcome)
    st.caption(
        "The register is treated as evidence, not approval. Results are recommendations for engineering review; "
        "final approval belongs to the authorized owner."
    )

    rows = build_rows(prep, outcome)
    tab_changes, tab_impact = st.tabs(["1 · What changed", "2 · Affected tests"])
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


main()
