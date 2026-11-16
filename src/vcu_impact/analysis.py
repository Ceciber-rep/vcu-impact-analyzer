"""Run the LLM impact assessment and apply deterministic post-checks."""

from __future__ import annotations

import re
from datetime import UTC, datetime

from pydantic import BaseModel, Field

from vcu_impact.llm import LLMClient
from vcu_impact.models import (
    ChangeNature,
    Confidence,
    ImpactStatus,
    LinkStatus,
    LLMImpactResult,
    RequiredAction,
    SpecDiff,
    SpecDocument,
    TestAssessment,
    TestRegister,
)
from vcu_impact.prompt import PROMPT_VERSION, SYSTEM_PROMPT, build_user_prompt

# Words that would turn a recommendation into a claim of approval.
_APPROVAL_RE = re.compile(r"\b(approved|approve|certified|signed[- ]off|sign[- ]off|accepted for release)\b", re.I)
# Negated forms are fine ("not approved", "does not approve", "approval remains with the owner").
_NEGATED_RE = re.compile(
    r"\b(not|cannot|can.t|never|no|without|pending|until|before|unless|remains? with|owner)\b[^.]{0,40}$", re.I
)


class AnalysisRun(BaseModel):
    """An LLM assessment plus provenance and post-check findings."""

    model_label: str
    prompt_version: str = PROMPT_VERSION
    created_at: str = Field(default_factory=lambda: datetime.now(UTC).isoformat(timespec="seconds"))
    latency_s: float | None = None
    attempts: int = 1
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    structured_mode: str = ""
    result: LLMImpactResult
    warnings: list[str] = Field(default_factory=list)
    raw_text: str = ""


def approval_language(text: str) -> list[str]:
    hits = []
    for m in _APPROVAL_RE.finditer(text):
        before = text[max(0, m.start() - 60) : m.start()]
        if not _NEGATED_RE.search(before):
            hits.append(text[max(0, m.start() - 40) : m.end() + 20].strip())
    return hits


_BROKEN_LINKS = {LinkStatus.MISSING, LinkStatus.TBD, LinkStatus.UNKNOWN, LinkStatus.REMOVED}
_ACTION_ORDER = list(RequiredAction)


def normalize_actions(
    test_id: str, status: ImpactStatus, actions: list[RequiredAction], link_broken: bool, warnings: list[str]
) -> list[RequiredAction]:
    """Make required_actions consistent; fix_link is decided by the parsed links only."""
    acts = set(actions)
    if RequiredAction.FIX_LINK in acts and not link_broken:
        warnings.append(f"{test_id}: removed fix_link set by the LLM; the requirement link is valid.")
    acts.discard(RequiredAction.FIX_LINK)
    if link_broken:
        acts.add(RequiredAction.FIX_LINK)
    if len(acts) > 1:
        acts.discard(RequiredAction.NONE)
    if not acts:
        acts.add(RequiredAction.NONE)
    if status == ImpactStatus.NOT_AFFECTED and acts & {RequiredAction.RERUN, RequiredAction.UPDATE_PROCEDURE}:
        warnings.append(f"{test_id}: status not_affected but actions {sorted(a.value for a in acts)}; check it.")
    return [a for a in _ACTION_ORDER if a in acts]


def post_check(result: LLMImpactResult, diff: SpecDiff, register: TestRegister) -> tuple[LLMImpactResult, list[str]]:
    """Enforce coverage, ID integrity and action consistency; never silently invent an assessment."""
    warnings: list[str] = []
    expected = [t.test_id for t in register.tests]
    changed = {c.req_id for c in diff.requirement_changes}
    broken = {t.test_id: any(link.status in _BROKEN_LINKS for link in t.links) for t in register.tests}
    by_id: dict[str, TestAssessment] = {}
    for a in result.assessments:
        if a.test_id not in expected:
            warnings.append(f"LLM returned an unknown test ID {a.test_id!r}; ignored.")
            continue
        if a.test_id in by_id:
            warnings.append(f"LLM returned {a.test_id} twice; kept the first.")
            continue
        bad = [r for r in a.related_requirements if r not in changed]
        if bad:
            warnings.append(f"{a.test_id}: removed non-changed requirement IDs {bad} from related_requirements.")
            a = a.model_copy(update={"related_requirements": [r for r in a.related_requirements if r in changed]})
        for hit in approval_language(" ".join([a.reason, a.recommended_action, *a.evidence])):
            warnings.append(f"{a.test_id}: approval-like wording in LLM output: '{hit}'")
        actions = normalize_actions(a.test_id, a.status, a.required_actions, broken[a.test_id], warnings)
        by_id[a.test_id] = a.model_copy(update={"required_actions": actions})

    for test_id in expected:
        if test_id not in by_id:
            warnings.append(f"LLM returned no assessment for {test_id}; marked needs_human_review.")
            by_id[test_id] = TestAssessment(
                test_id=test_id,
                status=ImpactStatus.NEEDS_HUMAN_REVIEW,
                confidence=Confidence.LOW,
                related_requirements=[],
                required_actions=normalize_actions(
                    test_id,
                    ImpactStatus.NEEDS_HUMAN_REVIEW,
                    [RequiredAction.OWNER_DECISION],
                    broken[test_id],
                    [],
                ),
                reason="No assessment was produced by the model for this test (added by post-check).",
                evidence=[],
                recommended_action="Assess this test manually.",
            )

    # Consistency between the model's own change interpretation and its test statuses:
    # if every requirement a test relates to was judged an editorial rewording, the test
    # cannot be directly affected. The status is left as the model gave it; the
    # contradiction is surfaced so a human looks at it.
    nature = {i.requirement_id: i.nature for i in result.change_interpretations}
    for a in by_id.values():
        related = a.related_requirements
        if (
            a.status == ImpactStatus.DIRECTLY_AFFECTED
            and related
            and all(nature.get(r) == ChangeNature.REWORDED_SAME_MEANING for r in related)
        ):
            warnings.append(
                f"{a.test_id}: marked directly_affected, but the change to {', '.join(related)} was interpreted "
                "as a rewording with the same meaning. Contradiction in the model output; review manually."
            )

    interp_ids = {i.requirement_id for i in result.change_interpretations}
    for missing in changed - interp_ids:
        warnings.append(f"LLM gave no interpretation for changed requirement {missing}.")
    cleaned = result.model_copy(update={"assessments": [by_id[t] for t in expected]})
    return cleaned, warnings


def run_analysis(client: LLMClient, diff: SpecDiff, revised: SpecDocument, register: TestRegister) -> AnalysisRun:
    call = client.structured(SYSTEM_PROMPT, build_user_prompt(diff, revised, register), LLMImpactResult)
    result, warnings = post_check(call.parsed, diff, register)
    return AnalysisRun(
        model_label=client.config.label,
        latency_s=round(call.latency_s, 2),
        attempts=call.attempts,
        prompt_tokens=call.prompt_tokens,
        completion_tokens=call.completion_tokens,
        structured_mode=call.structured_mode,
        result=result,
        warnings=call.notes + warnings,
        raw_text=call.raw_text,
    )
