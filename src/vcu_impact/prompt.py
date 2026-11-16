"""Prompt construction for the impact assessment.

The model receives the deterministic facts (diff, parsed links, extracted
values) as JSON, so it reasons over clean data instead of re-parsing documents,
and the raw register text, so it can read what the parser cannot interpret.
"""

from __future__ import annotations

import json

from vcu_impact.models import SpecDiff, SpecDocument, TestRegister

PROMPT_VERSION = "v3"  # earlier versions are frozen in eval/prompts/<version>/

SYSTEM_PROMPT = """\
You are a verification engineer assistant. You assess how a specification change
affects the existing tests in a test register. Your output feeds an engineering
impact report that a human owner will review. You give recommendations; you never
approve, accept or sign off anything.

For EVERY test in the register give a status (how strongly the test is tied to
the change) and required_actions (what the engineer has to do). Keep the two
separate: a test can be directly affected while its old evidence remains valid.

Status (relevance of the test to THIS change):
- directly_affected: the test verifies behaviour that the change alters. If the
  change alters no behaviour (an editorial rewording with the same meaning), no
  test is directly affected by it.
- possibly_affected: the test plausibly exercises the changed behaviour, but the
  relation is indirect or the evidence is insufficient to decide.
- needs_human_review: the test content might relate to the change, but the
  available information cannot settle it (e.g. a missing or TBD link on a test
  that touches the changed behaviour, a link to a removed requirement, unclear
  ownership). A broken link ALONE is not a reason for this status: the
  application already flags broken links with fix_link. A test whose content is
  clearly unrelated to the change is not_affected, whatever its link.
- not_affected: the test does not exercise the changed behaviour. Still give the
  reason.

required_actions (one or more; use ["none"] alone when nothing is needed):
- rerun: the previous evidence no longer meets the new requirement, does not
  record what the new requirement needs (e.g. no timing), or the test was never
  run for it.
- update_procedure: a threshold, script, stimulus or expected outcome in the
  procedure must change. Use it WITHOUT rerun when the old evidence still meets
  the new requirement (e.g. a relaxed limit).
- owner_decision: a human must decide, e.g. retire or re-scope a test whose
  requirement was removed, or clarify ownership.
- none: nothing to do for this change.
Do not output fix_link: the application adds it from the parsed links.

Rules:
1. Judge relevance from the test content (name, procedure, result, comment), not
   only from the requirement link. A missing, TBD or unknown link is not proof
   that a test is unrelated, and a valid link to an unchanged requirement does
   not rule out relevance.
2. Compare a measured value only with a limit on the SAME quantity measured the
   SAME way. Read the workshop notes: they may say that two quantities use
   different clocks or must not be conflated. Do not compare percentages (e.g.
   pedal position) with times.
3. Consider the direction of a change. A tightened limit can invalidate previous
   PASS evidence whose value no longer meets the new limit. A relaxed limit
   usually keeps passing evidence valid, though procedures or scripts may need
   alignment. An editorial rewording with the same meaning usually affects
   nothing.
4. A previous PASS is evidence from an earlier campaign, not approval, and it
   may not apply to a newer requirement. Never state that a test, a result or the
   change is approved, accepted, certified or signed off; final approval belongs
   to the authorized owner.
5. In related_requirements list only IDs of CHANGED requirements given in the
   input (empty list if none). Do not invent requirement or test IDs.
6. Confidence: high when the link and evidence are explicit; medium when the
   judgment relies on reasonable inference; low when information is missing or
   contradictory.
7. Keep each reason to 1-3 sentences and cite concrete evidence (values,
   comments, notes). recommended_action is one concrete next step, consistent
   with required_actions.
8. Also give, for each changed requirement, its nature (tightened, relaxed,
   reworded_same_meaning, scope_changed, added, removed, other) and a short
   engineering summary of what the change means for verification.
"""


def build_payload(diff: SpecDiff, revised: SpecDocument, register: TestRegister) -> dict:
    changes = []
    for c in diff.requirement_changes:
        changes.append(
            {
                "requirement_id": c.req_id,
                "change_type": c.change_type.value,
                "old_title": c.old.title if c.old else None,
                "new_title": c.new.title if c.new else None,
                "old_text": c.old.text if c.old else None,
                "new_text": c.new.text if c.new else None,
                "numeric_changes": [{"unit": n.unit, "old": n.old_text, "new": n.new_text} for n in c.numeric_changes],
            }
        )
    changed_ids = {c.req_id for c in diff.requirement_changes}
    return {
        "specification": {
            "baseline_revision": diff.baseline_revision,
            "revised_revision": diff.revised_revision,
        },
        "changed_requirements": changes,
        "unchanged_requirements": [
            {"requirement_id": r.req_id, "title": r.title, "text": r.text}
            for r in revised.requirements
            if r.req_id not in changed_ids
        ],
        "other_document_changes": [
            {"section": s.name, "old": s.old_text, "new": s.new_text}
            for s in diff.section_changes
            if s.name not in ("Front matter", "Document record")
        ],
        "register_header": register.title_lines,
        "tests": [
            {
                "test_id": t.test_id,
                "name": t.name,
                "procedure": t.procedure,
                "requirement_reference_raw": t.raw_reference,
                "parsed_links": [{"id": link.req_id, "status": link.status.value} for link in t.links],
                "previous_result": t.result_raw,
                "parsed_verdict": t.result_verdict,
                "extracted_values": [f"{m.value:g} {m.unit} (from {m.source})" for m in t.measurements],
                "owner": t.owner,
                "last_run": t.last_run,
                "comment": t.comment,
            }
            for t in register.tests
        ],
        "workshop_notes": [n.model_dump() for n in register.notes],
    }


def build_user_prompt(diff: SpecDiff, revised: SpecDocument, register: TestRegister) -> str:
    payload = build_payload(diff, revised, register)
    ids = ", ".join(t.test_id for t in register.tests)
    return (
        "Assess the impact of the specification change below on every test.\n"
        f"The register contains exactly these tests: {ids}. Return one assessment per test.\n\n"
        "INPUT (JSON):\n" + json.dumps(payload, indent=1, ensure_ascii=False)
    )
