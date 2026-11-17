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
(verified in the stored raw outputs of all qwen runs; the other three models follow the
schema order and write the interpretations first). The model therefore cannot use its own
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
- **Free-tier dependency.** Latency, rate limits and availability were observed on
  2026-11-16 and can change without notice. The Groq per-minute token cap causes waits of
  1 to 4 minutes when analyses run back to back. Gemini 3.5 Flash is the configured
  fallback, and replay mode needs no provider.
