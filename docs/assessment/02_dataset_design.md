# Phase 2: evaluation data design (decision document, awaiting approval)

## Recommendation check

The owner's recommendation (reuse S1-S10; no LLM-generated labels; a few new labelled scenarios; a separate unlabelled
robustness set) is **confirmed**, with four corrections from the evidence:

1. **S1-S10 are less independent than ten scenarios suggest.** S1, S9 and S10 all contain the real DR-01 100 -> 80 ms change;
   S8 and S4 touch DR-01 too. Many "critical" cells (TV-004 brake clock trap, TV-012, TV-007) are near-copies across them.
   Counts will be reported as cells **and** distinct cells (a cell is distinct by test + change type + `why` reasoning).
2. **S8-S10 are no longer unseen.** They were scored, discussed and used in the tie-break decision, and their labels were written
   by the assistant and never reviewed by the owner (S8 TV-002 was contradicted by two models). They stay in the regression set
   but cannot be called held-out for any new claim. Only the new scenarios written now are held-out for this assessment.
3. **The new labels are also written by the assistant**, so they share that weakness. Mitigation: labels with a `why` per cell are
   committed before any model runs, and the owner reviews them at this gate (cheap: about 6 scenarios).
4. **Unit equivalence is a known software defect (F-001), not an LLM question.** The unit scenario therefore measures how the
   LLM copes with a false numeric alarm, and is also covered by a deterministic unit test.

## Three families

| Family | Purpose | Labels | Where | Run when |
|---|---|---|---|---|
| a) Labelled scenarios | measure LLM judgement | yes, hand-written, `why` per cell | `eval/dataset.yaml` (new ids N1-N6, `held_out: true`), files under `eval/scenarios/` | phase 4, live models |
| b) Robustness inputs | software must not crash and must give clear errors | none (expected behaviour is in the test) | generated inside `tests/test_robustness_*.py` from code (no binary fixtures to maintain), plus a fake LLM client for provider failures | every `pytest` run, offline |
| c) UI flows | what the reviewer will click | expected result per flow in `docs/demo_script.md` | `eval/ui_flows.py` (AppTest; replay or live) and `tests/test_ui_flows.py` (replay, offline) | on demand / every `pytest` run |

## a) Proposed new labelled scenarios (6)

All are "baseline + one revision change, analysed against the provided register" like S1-S10, so the harness works unchanged.
The harness needs two small additions (not frozen files): a `drop_test` register edit (N5) and a multi-paragraph requirement in
the generated .docx (N4). Expected behaviour below is a summary; the cell labels come after approval.

| Id | Change | What it tests | Expected shape |
|---|---|---|---|
| N1 | DR-01 `100 milliseconds` -> `0.1 seconds` (same value, other unit) | false numeric alarm: the diff reports a change, the meaning is identical; also blocks the rewording safety net by design | all tests N (TV-001 N or P at most) |
| N2 | DR-02 title only (`Driver input validation` -> `Pedal input plausibility`), text identical | title-only change | all N; no test directly affected |
| N3 | add VCU-THM-07 and remove VCU-LOG-05 in the same revision | two change types at once; TV-006 now links to a removed requirement; TV-007 (thermal) relates to the new one | TV-006 R/D with owner decision; TV-007 P/R; rest N |
| N4 | BRK-03 gets a second paragraph ("The override shall also apply while a diagnostic fault is active.") | multi-paragraph requirement edit | TV-002/TV-011 P/D; TV-004 N (clock trap) |
| N5 | edit LOG-05 (record the build identifier **and** the calibration version) with its only test (TV-006) dropped from the register | change in a requirement no test references | all N; a good answer mentions that nothing verifies LOG-05 |
| N6 | rename: VCU-LOG-05 disappears, VCU-LOG-15 appears with the same text | ID rename; TV-006 link now dangles | TV-006 R (link to fix, owner decision), related requirement should name LOG-15; others N |

Held-out rules: committed with labels and `why` before any model run; not used for prompt wording; if a result is surprising the
label is not changed afterwards (a correction would be a separate, dated commit).

## b) Robustness inputs (no labels)

Generated in code and run offline: identical specs, same file twice, swapped baseline/revised, duplicate/renamed/odd IDs, empty
body, very long text, unit and number formats, Word documents with tracked changes, comments, tables, headers, text boxes, other
heading styles, corrupt / empty / wrong-extension / encrypted / `.doc` / large files, register variants (column order, extra
columns, merged cells, hidden sheet, blank rows, formulas without cached values, text numbers, 0 / 1 / ~200 tests, multi-ID link
cells, lowercase IDs, "N/A", "see notes"), a fake LLM client for provider-down / invalid key / timeout / 413 / 429 / schema rejection /
truncation / omitted tests / invented IDs / empty answer, prompt injection strings, HTML injection strings in the UI and exports.
These are phase 3 and need no decision.

## c) UI flows

F0-F7 already exist (`eval/ui_flows.py`). Add a replay-only pytest version using a stub `analyze` so the flows run offline in CI,
plus one "edit then revert" flow.

## Naive baseline (recommended: yes, about 40 minutes)

A rule-only assessor, no LLM: a test is D if its parsed link is a changed requirement; P if its text/result contains a number
with the same unit as a changed number but has no link; R if its link is broken (missing/TBD/unknown/removed); otherwise N.
It writes pseudo run files in the harness's own format under a new results folder, so the existing scorer, raw and post-check
views, and critical-cell counts apply without change. Value: shows what the LLM adds (expected: it finds TV-003 and the traps
only if they are cheap to catch, and falls for TV-004 "88 ms" and TV-007 "80 %"). Cost: one small module plus a scorer entry.

## Decisions requested

1. Approve the six scenarios (or change the list). Alternative if time is short: N1, N3, N6 only.
2. Approve the naive baseline.
3. Accept that the labels are assistant-written and will be reviewed by you before any model runs on them.

Time note: the stated budget (45 minutes) is already exceeded by phases 0-2; phases 3-4 (live model runs under the Groq
limits found in F-002) will take longer. Say if you want phase 4 reduced (for example 3 repeats instead of 5, one perturbation type).
