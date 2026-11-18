# Phase 4: LLM evaluation of the application as shipped

**What was tested:** the application path, not isolated models: `pipeline.prepare` then `pipeline.analyze(mode="live")` (the UI's "Run analysis"),
Groq `qwen/qwen3.8-27b` primary, Gemini 3.5 Flash fallback, prompt v3, schema and post-check unchanged (frozen). Calls were paced 65 s apart.
Runner `eval/assess_run.py`, analysis `eval/assess_analyze.py`, raw results `eval/results/assessment/app-groq-gemini/` (new folder; nothing under
the frozen `eval/results/v1-v3` was touched), generated tables `docs/assessment/results/phase4_tables.md` and `.json`.
Labels: S1-S10 as committed before; N1-N6 written by the assistant and confirmed by the project owner before any model ran.

## The run is incomplete (read this first)

32 cases were planned. **15 answered, 17 failed** (both providers refused). All 17 failures are recorded in `availability_log.jsonl`.

| Missing | Why it matters |
|---|---|
| S2, S5, **N1** (base cases) | S5 is the known rewording failure; N1 is the unit-equivalence scenario |
| S1 repeats r3-r5, N4 repeats r2-r5 | consistency evidence is thin |
| Perturbations P1, P3, P4 on S1; all four on N4 | only P2_S1 (shuffled workshop notes) ran |

Cause: Groq's free tier allows 200,000 tokens per day and about 6,000 tokens are used per analysis; the daily cap (and, for 3 early cases, the
1,000 output-tokens-per-minute cap) was reached after about 15 analyses in this session on top of the earlier day's use. Gemini answered **every**
fallback attempt with a bare HTTP 429 (cause not determined: daily quota or rate limit; not verified). So **the fallback rescued 0 of 17 failures**.
This is itself a finding (F-022). Completing the run needs quota: `uv run python eval/assess_run.py` resumes and only runs missing cases
(about 17 more analyses, roughly 105,000 Groq tokens).

All numbers below are therefore from 13 base scenarios (8 of S1-S10, 5 of N1-N6), 2 runs of S1, 1 perturbation. Treat them as indicative, not as a ranking.

## Accuracy (first run per scenario; counts, 95% Wilson intervals)

"Distinct" = unique (test, accepted set, preferred answer, label reasoning); many cells are near-copies. "Acceptable" = inside the label's accepted set.

| Source (view) | Set | Judgments (distinct) | Acceptable | Preferred | Critical cells ok | Missed impacts | Over-flags |
|---|---|---|---|---|---|---|---|
| **Application** (raw) | S, 8 of 10 scenarios | 97 (64) | 95/97 = 98% (93-99) | 72/97 = 74% (65-82) | 26/27 = 96% (82-99) | 0 | 2 |
| **Application** (post-check) | S, 8 of 10 | 97 (64) | 95/97 = 98% | 72/97 = 74% | 26/27 = 96% | 0 | 2 |
| **Application** (raw) | N, held out, 5 of 6 | 59 (23) | 56/59 = 95% (86-98) | 46/59 = 78% (66-87) | **5/7 = 71% (36-92)** | 0 | 3 |
| **Application** (post-check) | N, held out, 5 of 6 | 59 (23) | 57/59 = 97% (88-99) | 47/59 = 80% | 6/7 = 86% (49-97) | 0 | 2 |
| Rule-only baseline | S, all 10 | 121 (69) | 99/121 = 82% (74-88) | 71/121 = 59% | **22/32 = 69% (51-82)** | 0 | 4 |
| Rule-only baseline | N, all 6 | 71 (29) | 62/71 = 87% (78-93) | 44/71 = 62% | 6/9 = 67% (35-88) | 0 | 4 |
| Frozen v3 Groq (earlier, all S) | S, all 10 | 121 (69) | 119/121 = 98% (94-100) | 91/121 = 75% | 30/32 = 94% (80-98) | 0 | 2 |
| Frozen v3 Gemini (earlier, all S) | S, all 10 | 121 (69) | 118/121 = 98% (93-99) | 97/121 = 80% | 31/32 = 97% (84-99) | 0 | 3 |

What the numbers say, honestly:
- **No missed impact** in any LLM run (0 of 156 judgments); this is the error type that matters most.
- The rule-only baseline looks fine on "acceptable" (82-87%) because most cells are easy "not affected"; on **critical** cells it reaches 69% and 67%, against 96% and 71-86% for the application. The N-set difference is small and the intervals overlap widely (9 and 7 critical cells): **the LLM's advantage is clear on S1-S10 and not demonstrated on N1-N6 with this sample**.
- The intervals are wide; the preferred-answer rate (74-80%) is mostly P versus D or R choices, which the labels accept.
- Models: only the primary model answered, so "per model" accuracy on the new scenarios exists for Groq only. The earlier frozen runs show Groq and Gemini equal within noise on S1-S10.

## Error analysis (every wrong cell of the application, raw view: 5 of 156)

| Cell | Got (conf.) | Category | What happened |
|---|---|---|---|
| N2 TV-010 (critical) | directly affected (high) | over-flag, **self-contradiction** | title-only change; the model's own reason says "editorial rewording ... evidence remains unchanged" yet marks it directly affected. The post-check corrected it (an `Adjustment` is recorded). |
| N6 TV-006 (critical) | directly affected (high), actions update_procedure + fix_link | over-flag and wrong action | rename of LOG-05 to LOG-15; the reason says the PASS evidence "remains valid ... only the link must be updated", but it still asks to update the procedure. Not corrected by any check |
| S8 TV-002 (critical, label contested before) | directly affected (high) | over-flag | the reason itself says the 85 % stimulus is below the new 90 % trigger, so the test no longer exercises the change |
| N4 TV-004 | directly affected (high) | over-flag | brake latency test without a fault; the model reasons it lacks the new fault condition |
| S4 TV-003 | directly affected (medium) | over-flag | no link, content related; acceptable alternatives were N/P/R |

Other constraint failures: required actions 19/21 met (S1 TV-002 gets `owner_decision` without `rerun`; N6 TV-006 above); related requirements 9/10 met (S9 TV-002 omits VCU-DR-01).
Categories not observed: missed impact (0), wrong related requirement beyond the one above, hallucinated evidence (below), clock or arithmetic confusion in the application run (the TV-004 brake-clock trap and the TV-007 "80 %" trap were handled in every answered scenario).
Pattern worth acting on: **2 of the 5 errors are "the reason says nothing changed, the status says directly affected"** (S5 earlier, N2 now): the failure is systematic for rewording-like changes, not a one-off, and the application's safety net depends on the model's own `nature` reading (F-024).

## Evidence grounding

Evidence strings are paraphrases, so a verbatim match is the wrong test (0 of 428 strings are verbatim quotes). Checked instead: numbers and IDs in the evidence against the input
the model received, and "unchanged" claims against the diff. 238 of 428 strings (56%) contain a number or ID that can be checked; **0 of 238 contain one that is not in the input**, and **0**
sentences call a changed requirement "unchanged". The other 44% carry nothing checkable, so this does not prove the reasoning is right (see N6, S8). Not verified: a human read of all 428 strings.

## Consistency and perturbation

- S1 repeated: 5 runs of the same input and prompt with the primary model (3 frozen v3 runs plus 2 from this run): **12/12 tests with the same status in all runs**. At temperature 0 identical answers on identical input show determinism, not robustness.
- Perturbation, 1 of 8 run: shuffled workshop notes on S1 changed 1 of 12 statuses (TV-003 possibly affected to needs human review, both accepted). Shuffled rows, harmless formatting and renamed test ids: **not verified** (quota).
- Earlier phase 1 runs on edited inputs show a model-dependent reading of the same change (F-007), which the primary-only data here cannot resolve.

## Reliability

| Measure | Result |
|---|---|
| Cases answered | 15 of 32 (47%); all answers from Groq; fallback used 0 times, rescued 0 of 17 failures |
| First attempt failed | 24 of 32 (75%) in this session; 17 still failed after the 90 s retry |
| Failure causes | Groq 429: 3 early cases per-minute output limit (1,000 tokens), 13 daily limit (200,000 tokens); 1 invalid JSON twice; Gemini bare 429 every time |
| Valid on first try (of answered) | 14 of 15; 1 provider-side schema rejection repaired |
| Omitted tests, invented IDs, approval wording | 0, 0, 0 (warnings counted over 15 runs) |
| Latency of answered runs | median 5.3 s, p90 13.0 s, max 18.9 s (Groq). One failed case took **3,618 s** before reporting failure (F-023) |
| Rate-limit waits | the application does not wait: a 429 is retried by the SDK (2 short retries) and then the fallback is tried |
| Cost of a failure to the user | "Not analysed" banner with the provider text; the register facts and the diff remain; no wrong result is shown. The user cannot do anything but wait (daily cap) or switch provider |

## Confidence calibration (application, all answered cells, raw view)

| Confidence | Cells | Wrong | Wrong rate |
|---|---|---|---|
| high | 120 | 4 | 3% (1-8%) |
| medium | 26 | 1 | 4% (1-19%) |
| low | 10 | 0 | 0% (0-28%) |

"High" is not more reliable than "medium" here, and **3 of the 4 high-confidence errors are critical cells** (N2 TV-010, N6 TV-006, S8 TV-002). Confidence cannot be used to decide which answers to double-check (S3).

## Change interpretation (`nature`, `engineering_summary`)

Hand-checked labels `eval/nature_labels.yaml` (written before the analysis; S2 and S3 excluded as ambiguous) plus `expect_nature` of N1-N6: **13 of 14 readings correct (93%, 69-99%)**. The wrong one: S8 (trigger raised from 70 % to 90 %) read as `tightened`; the label accepts `scope_changed` or `relaxed` and is itself arguable.
All requirement changes with a numeric change had a summary that names the new value (6 of 6). Nature is stable on S1 (`tightened` in 2 of 2 runs here; unstable in older prompt versions). Because the post-check relies on `nature` and the sample is 14 readings, this is not enough to call the dependence safe; it was right on every rewording case it was needed for (N2, S5 earlier).

## Live versus replay

The committed recording of the default inputs (2026-11-16) and the live run of this assessment (S1) have **identical statuses for all 12 tests**. Phase 1 flows F1-F7 compared replay (always "not analysed" for edits) with live: replay cannot show an edited input by design.

## New findings

| ID | Sev | Finding |
|---|---|---|
| F-022 | **S2** | Free-tier ceilings make the application unusable after roughly 30 analyses per day (Groq 200,000 tokens per day; about 6,000 per analysis) and per minute (1,000 output tokens); the Gemini fallback failed with a bare 429 on every attempt, so a demo after heavy use fails with "Not analysed" even though a fallback is configured. Needs an explicit plan: replay for the demo, cache hits, a visible "daily limit reached" message |
| F-023 | S2 | A failing call can block the UI for a very long time: one case took 3,618 s (600 s timeout, SDK retries, two attempts, then the fallback) with only a "this takes a few seconds to a few minutes" spinner and no cancel |
| F-024 | S2 | The model contradicts itself on rewording-like changes in 2 of the 3 such scenarios measured (S5, N2: reason says unchanged, status says directly affected); the correction depends on the unscored `nature` field, and the rename case (N6) shows a similar contradiction (evidence valid, update procedure) that no check catches |
| F-025 | S3 | Confidence does not separate right from wrong (3% of high-confidence cells wrong, 3 of 4 critical) |
| F-026 | S3 | The plan was not completed for lack of quota; no resume guard prevents a partially filled results folder from being mistaken for a complete one (the report states it) |

Totals now (26 findings): S1 1, S2 11, S3 10, S4 3 (S2 now: F-001, F-002, F-007, F-011, F-012, F-015, F-016, F-020, F-022, F-023, F-024).
