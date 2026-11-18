"""Rule-only baseline (no LLM): what requirement-ID matching plus numeric-unit matching can say.

    VCU_EVAL_DATASET=dataset.yaml            uv run python eval/naive_baseline.py --out assessment
    VCU_EVAL_DATASET=dataset_assessment.yaml uv run python eval/naive_baseline.py --out assessment

It writes run files in the same format as the model runs (eval/results/<out>/naive-baseline/), so the
existing scorer (raw and post-check views, critical cells, action constraints) applies unchanged.

Rules, in order, for each test:
  1. its link points to a requirement that was changed (added/modified) ........ directly_affected
  2. its link points to a requirement removed in the revision .................. needs_human_review
  3. the test text (procedure, result, comment) has a number whose unit also
     appears in a numeric change of the diff (e.g. "88 ms" vs a changed "ms") ..... possibly_affected
  4. its link is missing, TBD or unknown ....................................... needs_human_review
  5. otherwise ................................................................... not_affected
The rules read the same parsed register and diff that the application gives the LLM. They cannot read
workshop notes, cannot tell two clocks apart, and cannot see a test whose content relates to a change.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "eval"))
import evaluate as ev  # noqa: E402

from vcu_impact.analysis import AnalysisRun  # noqa: E402
from vcu_impact.diff import extract_quantities  # noqa: E402
from vcu_impact.models import (  # noqa: E402
    ChangeType,
    Confidence,
    ImpactStatus,
    LinkStatus,
    LLMImpactResult,
    RequiredAction,
    TestAssessment,
)

NAME = "naive-baseline"


def assess(prep) -> LLMImpactResult:
    changed = {c.req_id for c in prep.diff.requirement_changes if c.change_type != ChangeType.REMOVED}
    removed = {c.req_id for c in prep.diff.requirement_changes if c.change_type == ChangeType.REMOVED}
    changed_units = {n.unit for c in prep.diff.requirement_changes for n in c.numeric_changes if n.unit}
    out = []
    for t in prep.register.tests:
        valid = {link.req_id for link in t.links if link.status == LinkStatus.VALID}
        broken = [link for link in t.links if link.status != LinkStatus.VALID and link.status != LinkStatus.REMOVED]
        text = " ".join([t.procedure, t.result_raw, t.comment])
        units = {u for u, _, _ in extract_quantities(text) if u}
        if valid & changed:
            status, why, acts = (
                ImpactStatus.DIRECTLY_AFFECTED,
                f"linked to changed {sorted(valid & changed)}",
                ["rerun"],
            )
        elif any(link.req_id in removed or link.status == LinkStatus.REMOVED for link in t.links):
            status, why, acts = ImpactStatus.NEEDS_HUMAN_REVIEW, "linked requirement was removed", ["owner_decision"]
        elif units & changed_units:
            status, why, acts = (
                ImpactStatus.POSSIBLY_AFFECTED,
                f"same unit as a changed number {sorted(units & changed_units)}",
                ["owner_decision"],
            )
        elif broken or not t.links:
            status, why, acts = ImpactStatus.NEEDS_HUMAN_REVIEW, "link missing, TBD or unknown", ["owner_decision"]
        else:
            status, why, acts = (
                ImpactStatus.NOT_AFFECTED,
                "no link to a changed requirement, no matching unit",
                ["none"],
            )
        out.append(
            TestAssessment(
                test_id=t.test_id,
                status=status,
                confidence=Confidence.LOW,
                related_requirements=sorted(valid & changed),
                required_actions=[RequiredAction(a) for a in acts],
                reason=f"Rule-based: {why}.",
                evidence=[],
                recommended_action="Rule-based baseline; no engineering judgement.",
            )
        )
    return LLMImpactResult(change_interpretations=[], assessments=out)


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--out", required=True, help="results sub-folder under eval/results")
    args = p.parse_args()
    out_dir = ev.RESULTS / args.out / NAME
    out_dir.mkdir(parents=True, exist_ok=True)
    for sc in ev.load_dataset()["scenarios"]:
        prep = ev._prepared(sc)
        # Same post_check as for model runs (coverage and fix_link from the parsed links).
        from vcu_impact.analysis import post_check

        checked = post_check(assess(prep), prep.diff, prep.register)
        run = AnalysisRun(model_label=NAME, latency_s=0.0, result=checked.result, warnings=checked.warnings)
        (out_dir / f"{sc['id']}_r1.json").write_text(json.dumps({"ok": True, **run.model_dump(mode="json")}, indent=1))
        print(sc["id"], {a.test_id: ev.SHORT[a.status.value] for a in checked.result.assessments})


if __name__ == "__main__":
    main()
