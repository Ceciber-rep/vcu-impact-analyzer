# Known issues and limitations

Issues known in the current analysis configuration (prompt **v3**, Groq
`qwen/qwen3.8-27b`). Evidence for each is in [llm_evaluation.md](llm_evaluation.md) and
the raw outputs under `eval/results/v3/`.

## 1. A pure rewording can be reported as "directly affected" (open)

**Where it fails.** Scenario S5: VCU-DGN-04 is reworded with the same meaning
("unavailable" becomes "lost", "enter" becomes "switch", "log" becomes "record"). The
model correctly interprets the change as `reworded_same_meaning` and says in its own
reason that "the behavior is unchanged" and the previous evidence remains valid. It still
marks TV-005 as `directly_affected`, with required actions `["none"]`.

**Why.** Prompt v2 defined `directly_affected` as "the test verifies behaviour that the
change alters". The model reads "the change" as "the changed requirement": TV-005
verifies DGN-04, so it calls it directly affected. Prompt v3 added the sentence "if the
change alters no behaviour (an editorial rewording with the same meaning), no test is
directly affected by it". This did not change the answer. Prompt v1 (status only, without
`required_actions`) answered `not_affected` correctly.

**Impact.** The work is right: no re-run, no procedure change. The status is wrong and
alarming. This matters for demos, because rewording a requirement is a likely
"small change" to try.

**Mitigation in place.** A deterministic post-check (`analysis.post_check`) warns when a
test is `directly_affected` and every requirement it relates to was interpreted as
`reworded_same_meaning`. The status is **not** overridden, so a disagreement stays
visible instead of being hidden. The warning must be shown next to the test in the UI
and in the report.

**Not done, and why.** Further prompt wording was not tried. v3 was already tuned on the
same seven scenarios it is scored on, and another iteration would fit the dataset even
more.

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
