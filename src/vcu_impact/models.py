"""Data models shared by the parser, the diff, the LLM layer, the UI and the report.

Deterministic facts (parsed from the documents) and LLM judgments are kept in
separate models so the UI and the report can always show which is which.
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field

# ---------------------------------------------------------------------------
# Specification
# ---------------------------------------------------------------------------


class Requirement(BaseModel):
    req_id: str
    title: str
    text: str  # body text, paragraphs joined with a newline


class SpecSection(BaseModel):
    """A non-requirement part of the document (metadata table, context, notes)."""

    name: str
    text: str


class SpecDocument(BaseModel):
    source_name: str
    title: str = ""
    revision: str = ""
    requirements: list[Requirement]
    sections: list[SpecSection] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)  # input quality notes (e.g. tracked changes), shown to the user

    def requirement(self, req_id: str) -> Requirement | None:
        return next((r for r in self.requirements if r.req_id == req_id), None)

    @property
    def requirement_ids(self) -> list[str]:
        return [r.req_id for r in self.requirements]


# ---------------------------------------------------------------------------
# Diff
# ---------------------------------------------------------------------------


class ChangeType(StrEnum):
    ADDED = "added"
    REMOVED = "removed"
    MODIFIED = "modified"


class NumericChange(BaseModel):
    """A value with a unit whose number changed, e.g. 100 milliseconds -> 80 milliseconds."""

    unit: str
    old_value: float | None
    new_value: float | None
    old_text: str | None
    new_text: str | None


class RequirementChange(BaseModel):
    req_id: str
    change_type: ChangeType
    old: Requirement | None = None
    new: Requirement | None = None
    title_changed: bool = False
    numeric_changes: list[NumericChange] = Field(default_factory=list)


class SectionChange(BaseModel):
    name: str
    old_text: str | None
    new_text: str | None


class SpecDiff(BaseModel):
    baseline_name: str
    revised_name: str
    baseline_revision: str = ""
    revised_revision: str = ""
    requirement_changes: list[RequirementChange]
    unchanged_requirement_ids: list[str]
    section_changes: list[SectionChange]

    @property
    def has_requirement_changes(self) -> bool:
        return bool(self.requirement_changes)


# ---------------------------------------------------------------------------
# Test register
# ---------------------------------------------------------------------------


class LinkStatus(StrEnum):
    VALID = "valid"  # requirement exists in the revised spec
    REMOVED = "removed_in_revision"  # existed in the baseline, gone in the revision
    UNKNOWN = "unknown_requirement"  # not present in either spec (orphaned)
    TBD = "tbd"  # explicit placeholder, not validated
    MISSING = "missing"  # empty cell


class RequirementLink(BaseModel):
    raw: str
    req_id: str | None
    status: LinkStatus


class Measurement(BaseModel):
    value: float
    unit: str
    source: str  # which column it came from


class TestCase(BaseModel):
    test_id: str
    name: str
    procedure: str
    raw_reference: str
    links: list[RequirementLink]
    result_raw: str
    result_verdict: str  # PASS / FAIL / NOT RUN / UNKNOWN (deterministic parse)
    measurements: list[Measurement]
    owner: str
    last_run: str
    comment: str


class WorkshopNote(BaseModel):
    date: str
    author: str
    observation: str
    next_step: str


class TestRegister(BaseModel):
    source_name: str
    title_lines: list[str] = Field(default_factory=list)
    tests: list[TestCase]
    notes: list[WorkshopNote]


# ---------------------------------------------------------------------------
# LLM output (validated against a strict JSON schema)
# ---------------------------------------------------------------------------


class ImpactStatus(StrEnum):
    DIRECTLY_AFFECTED = "directly_affected"
    POSSIBLY_AFFECTED = "possibly_affected"
    NEEDS_HUMAN_REVIEW = "needs_human_review"
    NOT_AFFECTED = "not_affected"


class Confidence(StrEnum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class RequiredAction(StrEnum):
    """What the engineer has to do; separate from how strongly the test is tied to the change."""

    RERUN = "rerun"  # previous evidence invalid or silent for the new requirement
    UPDATE_PROCEDURE = "update_procedure"  # threshold/script/text must change; evidence may still hold
    FIX_LINK = "fix_link"  # traceability broken (set deterministically from the parsed links)
    OWNER_DECISION = "owner_decision"  # a human must decide (retire, re-scope, ownership)
    NONE = "none"


class ChangeNature(StrEnum):
    TIGHTENED = "tightened"
    RELAXED = "relaxed"
    REWORDED_SAME_MEANING = "reworded_same_meaning"
    SCOPE_CHANGED = "scope_changed"
    ADDED = "added"
    REMOVED = "removed"
    OTHER = "other"


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ChangeInterpretation(_Strict):
    requirement_id: str
    nature: ChangeNature
    engineering_summary: str = Field(
        description="One or two sentences: what changed and what it means for verification."
    )


class TestAssessment(_Strict):
    test_id: str
    status: ImpactStatus
    confidence: Confidence
    related_requirements: list[str] = Field(
        description="IDs of the changed requirements this judgment refers to; empty if none."
    )
    required_actions: list[RequiredAction] = Field(
        description="What the engineer must do: one or more of rerun, update_procedure, owner_decision; "
        "or [none]. fix_link is set by the application from the parsed links."
    )
    reason: str = Field(description="Short evidence-based explanation (1-3 sentences).")
    evidence: list[str] = Field(
        description="Short quotes or facts from the register, notes or spec supporting the reason."
    )
    recommended_action: str = Field(description="Concrete next step for the engineer.")


class LLMImpactResult(_Strict):
    change_interpretations: list[ChangeInterpretation]
    assessments: list[TestAssessment]
