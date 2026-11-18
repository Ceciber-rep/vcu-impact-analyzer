"""Run the LLM impact assessment and apply deterministic post-checks."""

from __future__ import annotations

import re
from datetime import UTC, datetime
from typing import NamedTuple

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


REWORDING_RULE = "rewording_contradiction"


class Adjustment(BaseModel):
    """A correction the application made to a model answer.

    It is kept outside the LLM schema on purpose: it records what the application did,
    not what the model said, so the UI and the report can show both side by side.
    """

    test_id: str
    rule: str
    original_status: ImpactStatus
    new_status: ImpactStatus
    reason: str


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
    adjustments: list[Adjustment] = Field(default_factory=list)  # empty for older recordings
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


class PostCheck(NamedTuple):
    result: LLMImpactResult
    warnings: list[str]
    adjustments: list[Adjustment]


def _reconcile_with_interpretation(
    a: TestAssessment, nature: dict[str, ChangeNature], numeric_changed: set[str], warnings: list[str]
) -> tuple[TestAssessment, Adjustment | None]:
    """Safety net for one known inconsistency in the model output.

    A test is not directly affected by a change that the model itself read as a rewording
    with the same meaning. This does not make the model better: it still contradicts itself,
    and the application corrects the status visibly (an Adjustment plus a warning).

    - all related requirements are pure rewordings: status becomes not_affected;
    - guard: never when the deterministic diff found a changed number in one of them, because
      the model's reading of the change (``nature``) is unscored and unstable, and a wrong
      "rewording" there would turn a correctly flagged test into a missed impact;
    - mixed related requirements: untouched;
    - no related requirement named while every change is a rewording: warning only.
    """
    if a.status != ImpactStatus.DIRECTLY_AFFECTED:
        return a, None
    reworded = ChangeNature.REWORDED_SAME_MEANING
    related = a.related_requirements
    if related and all(nature.get(r) == reworded for r in related):
        with_numbers = [r for r in related if r in numeric_changed]
        if with_numbers:
            warnings.append(
                f"{a.test_id}: marked directly_affected while the change to {', '.join(with_numbers)} was read as a "
                "rewording with the same meaning, but the diff found a changed number there. Not adjusted: the "
                "status stays as the model gave it; review manually."
            )
            return a, None
        reason = (
            f"The model read the change to {', '.join(related)} as a rewording with the same meaning, "
            "so a test related only to it cannot be directly affected."
        )
        warnings.append(
            f"{a.test_id}: status changed from directly_affected to not_affected by the application's "
            f"post-check, not by the model. {reason} The model's answer was inconsistent; review manually."
        )
        adjustment = Adjustment(
            test_id=a.test_id,
            rule=REWORDING_RULE,
            original_status=ImpactStatus.DIRECTLY_AFFECTED,
            new_status=ImpactStatus.NOT_AFFECTED,
            reason=reason,
        )
        return a.model_copy(update={"status": ImpactStatus.NOT_AFFECTED}), adjustment
    if not related and nature and all(n == reworded for n in nature.values()):
        warnings.append(
            f"{a.test_id}: marked directly_affected without naming a changed requirement, while every change "
            "was read as a rewording with the same meaning. Not adjusted; review manually."
        )
    return a, None


def post_check(result: LLMImpactResult, diff: SpecDiff, register: TestRegister) -> PostCheck:
    """Enforce coverage, ID integrity and consistency; never silently invent an assessment.

    Returns the cleaned result, the warnings, and the adjustments made to model statuses.
    """
    warnings: list[str] = []
    adjustments: list[Adjustment] = []
    expected = [t.test_id for t in register.tests]
    changed = {c.req_id for c in diff.requirement_changes}
    broken = {t.test_id: any(link.status in _BROKEN_LINKS for link in t.links) for t in register.tests}
    nature = {i.requirement_id: i.nature for i in result.change_interpretations}
    numeric_changed = {c.req_id for c in diff.requirement_changes if c.numeric_changes}
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
        a, adjustment = _reconcile_with_interpretation(a, nature, numeric_changed, warnings)
        if adjustment:
            adjustments.append(adjustment)
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

    interp_ids = set(nature)
    for missing in sorted(changed - interp_ids):
        warnings.append(f"LLM gave no interpretation for changed requirement {missing}.")
    cleaned = result.model_copy(update={"assessments": [by_id[t] for t in expected]})
    return PostCheck(cleaned, warnings, adjustments)


def run_analysis(client: LLMClient, diff: SpecDiff, revised: SpecDocument, register: TestRegister) -> AnalysisRun:
    call = client.structured(SYSTEM_PROMPT, build_user_prompt(diff, revised, register), LLMImpactResult)
    checked = post_check(call.parsed, diff, register)
    return AnalysisRun(
        model_label=client.config.label,
        latency_s=round(call.latency_s, 2),
        attempts=call.attempts,
        prompt_tokens=call.prompt_tokens,
        completion_tokens=call.completion_tokens,
        structured_mode=call.structured_mode,
        result=checked.result,
        warnings=call.notes + checked.warnings,
        adjustments=checked.adjustments,
        raw_text=call.raw_text,
    )
