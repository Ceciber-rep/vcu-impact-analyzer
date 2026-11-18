# Known issues and limitations

Issues known in the current analysis configuration (prompt **v3**, Groq
`qwen/qwen3.8-27b`). Evidence for each is in [llm_evaluation.md](llm_evaluation.md) and
the raw outputs under `eval/results/v3/`.

## 1. The model contradicts itself on a pure rewording (open in the model; corrected visibly by the application)

**Where it fails.** Scenario S5: VCU-DGN-04 is reworded with the same meaning
("unavailable" becomes "lost", "enter" becomes "switch", "log" becomes "record"). The
model correctly interprets the change as `reworded_same_meaning` and says in its own
reason that "the behavior is unchanged" and the previous evidence remains valid. It still
marks TV-005 as `directly_affected`, with required actions `["none"]`. This is still true
of the model: the prompt v3 wording meant to prevent it did not (prompt v1 got this case
right).

**Probable cause (not tested).** Groq `qwen/qwen3.8-27b` writes the JSON keys in
alphabetical order, so `assessments` is generated **before** `change_interpretations`
(verified on the stored raw outputs: 29 of 30 qwen runs; Gemini 3.5 Flash writes the
interpretations first in 21 of 21 runs, the local qwen3:8b in 9 of 9, gpt-oss-120b in 19 of 21). The model therefore cannot use its own
reading of the change when it writes the statuses. Whether reordering the fields removes
the contradiction has not been tested (see docs/llm_evaluation.md, section 8).

**Safety net in the application, not an improvement of the model.**
`analysis.post_check` applies one rule: if a test is `directly_affected` and **all** of its
`related_requirements` were interpreted as `reworded_same_meaning`, its status is changed to
`not_affected`. The change is never silent:
- an `Adjustment` (test, rule, original status, new status, reason) is recorded on the run,
  outside the LLM schema, and exposed on each result row as `adjustment`;
- a warning naming the test is added to the run;
- the model's own output is kept unchanged in the run's `raw_text`.

Tests with mixed related requirements (a rewording and a real change) are not touched. A
`directly_affected` test with no related requirement is only warned about, and only when every
change in the run was read as a rewording.

**Risk of the safety net.** It trusts the model's `nature` field, which is **not scored** in
the evaluation and is not stable: for S3 qwen answered `tightened` (prompt v1), `relaxed`
(v2) and `tightened` (v3), and the local qwen3:8b read the relaxation in S4 (100 → 120 ms) as
`tightened`. If a model ever reads a real change as `reworded_same_meaning` and marks an
affected test `directly_affected`, the rule would downgrade a true impact to `not_affected`.
The visible warning and adjustment record are what protect against that, so the UI and the
report must show them next to the test.

## 2. Other limitations of the v3 configuration

- **Rerun vs owner decision.** In S1 the model asked for `owner_decision` on TV-002
  (linked to DR-01, no timing in its old evidence), where `rerun` was expected. This is
  the only miss on the 16 labelled action cases.
- **`fix_link` and the model's text can differ.** `fix_link` is added by the code from the
  parsed links. The model's own recommendation can still read "No action required" (for
  example TV-012 in S1). The UI and report must label `fix_link` as coming from the
  register data.
- **Small, single-annotator evaluation.** 84 judgments, one register, labels written by
  one person and reviewed by the project owner. Differences of one to three judgments
  are not meaningful.
- **Prompt fitted to its test set.** v3's wording was written after reading v2's failures
  on the same scenarios. Behaviour on different documents is not measured.
- **The choice of primary model is a tie.** After the follow-up (docs/llm_evaluation.md,
  section 8), Groq qwen3.8-27b and Gemini 3.5 Flash are indistinguishable on the held-out
  scenarios (36/37, 15/16 critical, no missed impact, the same failed cell). The
  pre-registered rule keeps qwen only because ties go to it and because the rewording safety net
  is counted; on raw statuses Gemini has one critical failure fewer (1 against 2). qwen is kept
  for its speed (about 7 s against about 95 s per analysis).
- **Some labels may be too strict.** S8 TV-002 (85% pedal after the trigger was raised to 90%)
  was answered `directly_affected` by both strong models, against the label. As with S4 TV-001
  and S7 TV-007, the status `directly_affected` mixes "linked to the changed requirement" with
  "its evidence is invalidated". The held-out labels were written by the assistant and have not
  been reviewed by the project owner.
- **The free-tier alternative is clearly worse.** gpt-oss-120b on Groq had 3 missed impacts
  and fell for the "valid link, stimulus out of scope" case (S10 TV-013). One v3 analysis
  also uses about the whole 8,000 tokens-per-minute free-tier budget of that model.
- **No input-perturbation test.** qwen returns byte-identical output on repeated identical
  input, so its consistency figure says nothing about robustness to rephrased requirements
  or reordered register rows.
- **Free-tier dependency.** Latency, rate limits and availability were observed on
  2026-11-16 and can change without notice. The Groq per-minute token cap causes waits of
  1 to 4 minutes when analyses run back to back. Gemini 3.5 Flash is the configured
  fallback, and replay mode needs no provider.
