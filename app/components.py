"""Rendering helpers for the Streamlit app. Display only: no analysis logic here."""

from __future__ import annotations

import html

import pandas as pd
import streamlit as st

from vcu_impact.diff import word_diff
from vcu_impact.models import (
    ChangeInterpretation,
    ChangeType,
    ImpactStatus,
    LinkStatus,
    RequiredAction,
    RequirementChange,
    SpecDiff,
)
from vcu_impact.pipeline import AnalysisOutcome, TestImpactRow

STATUS_LABEL = {
    ImpactStatus.DIRECTLY_AFFECTED: "🔴 Directly affected",
    ImpactStatus.POSSIBLY_AFFECTED: "🟠 Possibly affected",
    ImpactStatus.NEEDS_HUMAN_REVIEW: "🔵 Needs human review",
    ImpactStatus.NOT_AFFECTED: "🟢 Not affected",
}
NOT_ANALYSED = "⚪ Not analysed"
ACTION_LABEL = {
    RequiredAction.RERUN: "Re-run test",
    RequiredAction.UPDATE_PROCEDURE: "Update procedure",
    RequiredAction.FIX_LINK: "Fix requirement link",
    RequiredAction.OWNER_DECISION: "Owner decision",
    RequiredAction.NONE: "None",
}
LINK_LABEL = {
    LinkStatus.VALID: "valid",
    LinkStatus.REMOVED: "requirement removed",
    LinkStatus.UNKNOWN: "unknown requirement",
    LinkStatus.TBD: "TBD (not validated)",
    LinkStatus.MISSING: "missing",
}
CHANGE_BADGE = {ChangeType.ADDED: "🟩 Added", ChangeType.REMOVED: "🟥 Removed", ChangeType.MODIFIED: "🟨 Modified"}

CSS = """
<style>
.diff { font-size: 1.02rem; line-height: 1.6; }
.diff del { background: #ffd7d5; color: #82071e; text-decoration: line-through; padding: 0 2px; }
.diff ins { background: #ccffd8; color: #055d20; text-decoration: none; padding: 0 2px; font-weight: 600; }
.chip { display: inline-block; border: 1px solid #c8c8c8; border-radius: 12px; padding: 1px 10px;
        margin: 2px 4px 2px 0; font-size: 0.9rem; }
.src { color: #666; font-size: 0.85rem; }
</style>
"""


def inject_css() -> None:
    st.markdown(CSS, unsafe_allow_html=True)


def diff_html(old: str, new: str) -> str:
    parts = []
    for op, text in word_diff(old, new):
        t = html.escape(text)
        parts.append(f"<del>{t}</del>" if op == "delete" else f"<ins>{t}</ins>" if op == "insert" else t)
    return f'<div class="diff">{"".join(parts)}</div>'


# ---------------------------------------------------------------------------
# Provenance
# ---------------------------------------------------------------------------


def provenance_banner(outcome: AnalysisOutcome) -> None:
    text = outcome.source_text
    if outcome.mode == "live":
        st.success(text, icon="⚡")
    elif outcome.mode in ("replay", "cached"):
        st.info(text, icon="⏯️")
    else:
        st.warning(text, icon="⚠️")
    for w in outcome.warnings:
        st.warning(w)


# ---------------------------------------------------------------------------
# Changes tab
# ---------------------------------------------------------------------------


def change_card(change: RequirementChange, interpretation: ChangeInterpretation | None) -> None:
    req = change.new or change.old
    with st.container(border=True):
        st.markdown(f"**{change.req_id} · {html.escape(req.title)}** &nbsp; {CHANGE_BADGE[change.change_type]}")
        if change.change_type == ChangeType.MODIFIED:
            if change.title_changed:
                st.markdown("Title: " + diff_html(change.old.title, change.new.title), unsafe_allow_html=True)
            st.markdown(diff_html(change.old.text, change.new.text), unsafe_allow_html=True)
        elif change.change_type == ChangeType.ADDED:
            st.markdown(f'<div class="diff"><ins>{html.escape(change.new.text)}</ins></div>', unsafe_allow_html=True)
        else:
            st.markdown(f'<div class="diff"><del>{html.escape(change.old.text)}</del></div>', unsafe_allow_html=True)

        nums = [n for n in change.numeric_changes if n.unit]
        if nums and change.change_type == ChangeType.MODIFIED:
            chips = "".join(
                f'<span class="chip">{html.escape(n.old_text or "—")} → {html.escape(n.new_text or "—")}</span>'
                for n in nums
            )
            st.markdown(f"Numeric changes: {chips}", unsafe_allow_html=True)
        if interpretation:
            st.markdown(
                f"**LLM interpretation:** {interpretation.nature.value.replace('_', ' ')} — "
                f"{html.escape(interpretation.engineering_summary)}"
            )


def changes_tab(diff: SpecDiff, outcome: AnalysisOutcome) -> None:
    c1, c2, c3, c4 = st.columns(4)
    count = {t: sum(c.change_type == t for c in diff.requirement_changes) for t in ChangeType}
    c1.metric("Modified", count[ChangeType.MODIFIED])
    c2.metric("Added", count[ChangeType.ADDED])
    c3.metric("Removed", count[ChangeType.REMOVED])
    c4.metric("Unchanged", len(diff.unchanged_requirement_ids))
    st.caption(f"{diff.baseline_revision or diff.baseline_name}  →  {diff.revised_revision or diff.revised_name}")

    interp = {i.requirement_id: i for i in outcome.run.result.change_interpretations} if outcome.run else {}
    if not diff.requirement_changes:
        st.info("No requirement was added, removed or modified.")
    for change in diff.requirement_changes:
        change_card(change, interp.get(change.req_id))

    if diff.section_changes:
        with st.expander(f"Other document changes ({len(diff.section_changes)}): revision label, notes, context"):
            for s in diff.section_changes:
                st.markdown(f"**{html.escape(s.name)}**")
                st.markdown(diff_html(s.old_text or "", s.new_text or ""), unsafe_allow_html=True)
    if diff.unchanged_requirement_ids:
        st.caption("Unchanged requirements: " + ", ".join(diff.unchanged_requirement_ids))


# ---------------------------------------------------------------------------
# Impact tab
# ---------------------------------------------------------------------------


def _link_text(row: TestImpactRow) -> str:
    return "; ".join(f"{link.req_id or link.raw or '(empty)'} ({LINK_LABEL[link.status]})" for link in row.test.links)


def _actions_text(row: TestImpactRow) -> str:
    if not row.assessment:
        return ""
    return ", ".join(
        ACTION_LABEL[a] + (" *" if a in row.actions_from_code else "") for a in row.assessment.required_actions
    )


def impact_summary(rows: list[TestImpactRow]) -> None:
    analysed = [r for r in rows if r.assessment]
    cols = st.columns(4)
    for col, status in zip(cols, ImpactStatus, strict=True):
        col.metric(STATUS_LABEL[status], sum(r.assessment.status == status for r in analysed))
    acts = [a for r in analysed for a in r.assessment.required_actions]
    cols = st.columns(4)
    for col, action in zip(
        cols,
        [RequiredAction.RERUN, RequiredAction.UPDATE_PROCEDURE, RequiredAction.FIX_LINK, RequiredAction.OWNER_DECISION],
        strict=True,
    ):
        col.metric(ACTION_LABEL[action], acts.count(action))


def impact_table(rows: list[TestImpactRow]) -> TestImpactRow | None:
    """Filterable table; returns the selected row."""
    f1, f2, f3 = st.columns([2, 2, 1])
    status_opts = list(STATUS_LABEL.values())
    chosen_status = f1.multiselect("Status", status_opts, default=status_opts, key="flt_status")
    action_opts = list(ACTION_LABEL.values())
    chosen_actions = f2.multiselect("Requires action", action_opts, key="flt_action", placeholder="Any action")
    only_warn = f3.checkbox("Only with warnings", key="flt_warn")

    visible = []
    for r in rows:
        label = STATUS_LABEL[r.assessment.status] if r.assessment else NOT_ANALYSED
        if r.assessment and label not in chosen_status:
            continue
        if chosen_actions and not (
            r.assessment and {ACTION_LABEL[a] for a in r.assessment.required_actions} & set(chosen_actions)
        ):
            continue
        if only_warn and not r.warnings:
            continue
        visible.append(r)

    df = pd.DataFrame(
        [
            {
                "Test": r.test.test_id,
                "Name": r.test.name,
                "Status": STATUS_LABEL[r.assessment.status] if r.assessment else NOT_ANALYSED,
                "Confidence": r.assessment.confidence.value if r.assessment else "",
                "Required actions": _actions_text(r),
                "Requirement link": _link_text(r),
                "Previous result": r.test.result_raw,
                "Warnings": f"⚠️ {len(r.warnings)}" if r.warnings else "",
            }
            for r in visible
        ]
    )
    if df.empty:
        st.info("No test matches the filters.")
        return None
    event = st.dataframe(
        df,
        hide_index=True,
        width="stretch",
        on_select="rerun",
        selection_mode="single-row",
        key="impact_table",
    )
    st.caption(
        "Select a row to see the explanation. * = action set by the application from the register "
        "links, not by the model."
    )
    selected = event.selection.rows if event and event.selection else []
    return visible[selected[0]] if selected else None


def detail_panel(row: TestImpactRow) -> None:
    t, a = row.test, row.assessment
    with st.container(border=True):
        st.subheader(f"{t.test_id} · {t.name}")
        if a:
            st.markdown(
                f"**{STATUS_LABEL[a.status]}** &nbsp;·&nbsp; confidence **{a.confidence.value}**"
                + (f" &nbsp;·&nbsp; relates to {', '.join(a.related_requirements)}" if a.related_requirements else "")
            )
            for w in row.warnings:
                st.warning(w)
            st.markdown(f"**Why (LLM):** {a.reason}")
            if a.evidence:
                st.markdown("**Evidence cited (LLM):**\n" + "\n".join(f"- {e}" for e in a.evidence))
            from_model = [ACTION_LABEL[x] for x in a.required_actions if x not in row.actions_from_code]
            from_code = [ACTION_LABEL[x] for x in row.actions_from_code]
            st.markdown("**Required actions**")
            st.markdown(f"- From the LLM: {', '.join(from_model) or '—'}")
            if from_code:
                st.markdown(f"- From the register data: {', '.join(from_code)} (the requirement link is broken)")
            st.markdown(f"**Recommended next step (LLM):** {a.recommended_action}")
        else:
            st.info("Not analysed by an LLM. The register facts below come from the parser.")

        values = ", ".join(f"{m.value:g} {m.unit} ({m.source})" for m in t.measurements)
        with st.expander("Register facts (parsed, no LLM)", expanded=a is None):
            st.markdown(
                f"- **Procedure:** {t.procedure}\n"
                f"- **Requirement reference:** `{t.raw_reference or '(empty)'}` → {_link_text(row)}\n"
                f"- **Previous result:** {t.result_raw or '(empty)'} (parsed verdict: {t.result_verdict})\n"
                f"- **Values found:** {values or '—'}\n"
                f"- **Owner / last run:** {t.owner or '—'} / {t.last_run or '—'}\n"
                f"- **Comment:** {t.comment or '—'}"
            )
