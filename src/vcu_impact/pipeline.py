"""From input files to a per-test impact view. Used by the UI, the CLI and the report.

inputs -> prepare() -> Prepared (parsed docs, diff, register, LLM input, cache key)
       -> analyze() -> AnalysisOutcome (live / replay / not analysed)
       -> build_rows() -> one TestImpactRow per test
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

from pydantic import BaseModel

from vcu_impact import cache
from vcu_impact.analysis import Adjustment, AnalysisRun, post_check, run_analysis
from vcu_impact.diff import diff_specs
from vcu_impact.llm import LLMClient, LLMConfig, LLMError, describe_failure, extract_json
from vcu_impact.models import (
    LLMImpactResult,
    RequiredAction,
    SpecDiff,
    SpecDocument,
    TestAssessment,
    TestCase,
    TestRegister,
)
from vcu_impact.prompt import PROMPT_VERSION, build_user_prompt
from vcu_impact.register_parser import parse_register
from vcu_impact.spec_parser import parse_spec

REPO = Path(__file__).resolve().parents[2]
DEFAULT_INPUT_DIR = REPO / "data" / "input"

Mode = Literal["live", "replay", "cached", "not_analysed"]


# ---------------------------------------------------------------------------
# Inputs
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class InputFile:
    name: str
    data: bytes = field(repr=False)

    @property
    def sha256(self) -> str:
        return hashlib.sha256(self.data).hexdigest()

    @classmethod
    def from_path(cls, path: str | Path) -> InputFile:
        path = Path(path)
        return cls(name=path.name, data=path.read_bytes())


@dataclass(frozen=True)
class Inputs:
    baseline: InputFile
    revised: InputFile
    register: InputFile


def default_inputs() -> Inputs:
    return Inputs(
        baseline=InputFile.from_path(DEFAULT_INPUT_DIR / "VCU_Spec_Baseline.docx"),
        revised=InputFile.from_path(DEFAULT_INPUT_DIR / "VCU_Spec_Revised.docx"),
        register=InputFile.from_path(DEFAULT_INPUT_DIR / "VCU_Test_Register.xlsx"),
    )


@dataclass
class Prepared:
    inputs: Inputs
    baseline: SpecDocument
    revised: SpecDocument
    diff: SpecDiff
    register: TestRegister
    user_prompt: str
    key: str
    input_warnings: list[str] = field(default_factory=list)  # e.g. tracked changes in a specification


def prepare(inputs: Inputs) -> Prepared:
    """Parse and diff. Deterministic and fast; raises ValueError on unusable files."""
    baseline = parse_spec(inputs.baseline.data, inputs.baseline.name)
    revised = parse_spec(inputs.revised.data, inputs.revised.name)
    if not revised.requirements:
        raise ValueError(f"No requirements found in {inputs.revised.name}")
    register = parse_register(inputs.register.data, revised, baseline, inputs.register.name)
    diff = diff_specs(baseline, revised)
    user_prompt = build_user_prompt(diff, revised, register)
    return Prepared(
        inputs,
        baseline,
        revised,
        diff,
        register,
        user_prompt,
        cache.analysis_key(user_prompt),
        [*baseline.warnings, *revised.warnings],
    )


# ---------------------------------------------------------------------------
# Analysis
# ---------------------------------------------------------------------------


class AnalysisOutcome(BaseModel):
    mode: Mode
    run: AnalysisRun | None = None
    reason: str = ""  # why there is no run, or a note on the source
    recording_label: str = ""
    warnings: list[str] = []

    @property
    def model_label(self) -> str:
        return self.run.model_label if self.run else ""

    @property
    def source_text(self) -> str:
        """One-line provenance for the UI and the report."""
        if self.mode == "live":
            return f"Live LLM analysis by {self.model_label} at {self.run.created_at}."
        if self.mode == "replay":
            label = f" ({self.recording_label})" if self.recording_label else ""
            return (
                f"Replayed: real output of {self.model_label} recorded at {self.run.created_at}{label}. "
                "No model was called now."
            )
        if self.mode == "cached":
            return f"From an earlier live run of {self.model_label} at {self.run.created_at} in this environment."
        return f"Not analysed by an LLM: {self.reason}"


def configured_llms() -> tuple[list[LLMConfig], list[str]]:
    """Primary and optional fallback from the environment, plus why any is unavailable."""
    import os

    configs, problems = [], []
    for prefix, role in (("LLM_", "primary"), ("LLM_FALLBACK_", "fallback")):
        if not os.getenv(f"{prefix}PROVIDER"):
            if role == "primary":
                problems.append("No model configured (LLM_PROVIDER is empty).")
            continue
        try:
            configs.append(LLMConfig.from_env(prefix=prefix))
        except LLMError as exc:
            problems.append(f"{role} model unavailable: {exc}")
    return configs, problems


def _replay(prep: Prepared) -> AnalysisOutcome | None:
    found = cache.find(prep.key)
    if not found:
        return None
    entry, source = found
    run = entry.run
    # Re-apply the deterministic post-checks to the recorded raw model output, so
    # improvements to the checks also apply to recordings.
    try:
        raw = LLMImpactResult.model_validate_json(extract_json(run.raw_text))
    except ValueError:
        raw = run.result
    checked = post_check(raw, prep.diff, prep.register)
    run = run.model_copy(
        update={"result": checked.result, "warnings": checked.warnings, "adjustments": checked.adjustments}
    )
    return AnalysisOutcome(mode="replay" if source == "recorded" else "cached", run=run, recording_label=entry.label)


def _live(prep: Prepared, configs: list[LLMConfig]) -> AnalysisOutcome:
    notes: list[str] = []
    for config in configs:
        try:
            run = run_analysis(LLMClient(config), prep.diff, prep.revised, prep.register)
        except Exception as exc:  # noqa: BLE001 - any provider failure moves on to the fallback
            notes.append(f"{config.label} failed: {type(exc).__name__}: {describe_failure(exc)}")
            continue
        if notes:
            run = run.model_copy(update={"warnings": [*notes, *run.warnings]})
        cache.save(cache.CacheEntry(key=prep.key, prompt_version=PROMPT_VERSION, run=run))
        return AnalysisOutcome(mode="live", run=run, warnings=notes)
    return AnalysisOutcome(
        mode="not_analysed",
        reason="every configured model failed. " + " ".join(notes) + " The changes and register facts are still shown.",
        warnings=notes,
    )


def analyze(prep: Prepared, mode: Literal["auto", "replay", "live"] = "auto") -> AnalysisOutcome:
    """``replay``: recordings only. ``live``: call the model. ``auto``: recording, else model if configured."""
    if not prep.diff.has_requirement_changes:
        return AnalysisOutcome(
            mode="not_analysed",
            reason="no requirement was added, removed or modified, so there is nothing to assess.",
        )
    if mode in ("auto", "replay"):
        found = _replay(prep)
        if found or mode == "replay":
            return found or AnalysisOutcome(
                mode="not_analysed",
                reason="no recorded analysis exists for these inputs. Run the analysis with a configured model.",
            )
    configs, problems = configured_llms()
    if not configs:
        return AnalysisOutcome(mode="not_analysed", reason=" ".join(problems))
    return _live(prep, configs)


# ---------------------------------------------------------------------------
# View model
# ---------------------------------------------------------------------------


class TestImpactRow(BaseModel):
    test: TestCase
    assessment: TestAssessment | None
    actions_from_code: list[RequiredAction]  # actions set deterministically, not by the model
    warnings: list[str]
    adjustment: Adjustment | None = None  # set when the application changed the model's status


def build_rows(prep: Prepared, outcome: AnalysisOutcome) -> list[TestImpactRow]:
    by_id = {a.test_id: a for a in outcome.run.result.assessments} if outcome.run else {}
    all_warnings = (outcome.run.warnings if outcome.run else []) + outcome.warnings
    adjustments = {x.test_id: x for x in (outcome.run.adjustments if outcome.run else [])}
    rows = []
    for test in prep.register.tests:
        assessment = by_id.get(test.test_id)
        from_code = (
            [RequiredAction.FIX_LINK] if assessment and RequiredAction.FIX_LINK in assessment.required_actions else []
        )
        pattern = re.compile(rf"\b{re.escape(test.test_id)}\b")
        rows.append(
            TestImpactRow(
                test=test,
                assessment=assessment,
                actions_from_code=from_code,
                warnings=[w for w in all_warnings if pattern.search(w)],
                adjustment=adjustments.get(test.test_id),
            )
        )
    return rows
