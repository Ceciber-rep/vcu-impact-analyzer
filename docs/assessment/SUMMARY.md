# Assessment summary (2026-11-18)

**Scope:** requirements audit against `docs/exercise_brief.docx`, edge-case and robustness tests, an LLM evaluation of the application as shipped
(Groq qwen3.8-27b with Gemini fallback, prompt v3), prioritised fixes, and finalisation. Details: files `00` to `05` in this folder.

## What was tested
- 8 UI flows driven through the real Streamlit UI (replay and live); 133 automated tests (113 pass, 21 documented defects as strict `xfail`, plus 1 older); clean-clone and Docker start; secret and approval-language scans over the tree and the git history.
- LLM: 6 new held-out scenarios (labels reviewed by the project owner before any model ran), a rule-only baseline, repeats and perturbations of the application path.

## What failed (26 findings: S1 1, S2 11, S3 10, S4 3 before fixes)
Brief: no requirement of the brief is violated. The one S1 finding was a silent loss of Word tracked changes (F-010). S2 findings: units in the diff, free-tier ceilings and an
hour-long hang, a stale "not analysed" after a browser refresh, silent loss of link IDs or duplicate test IDs, text boxes/tables/odd ID formats, and a systematic model
contradiction on rewording-like changes (F-024).

## What was fixed (8 findings, `05_improvements.md`)
F-010 tracked changes (read as accepted, with a warning), F-020 refresh, F-023/F-022/F-002/F-003 timeouts and readable provider failures without organisation ids,
F-015/F-016 register links and duplicates, F-001 unit-aware numbers, F-025 confidence caveat. Prompt v3, the LLM schema and the model choice are unchanged; no v4.

## What remains, and why
Documented as limitations (README "Known issues"): text boxes/tables, other ID formats, merged cells, uncached formulas, lower-case link IDs, raw upload errors,
approval-detector gaps, markdown rendering of untrusted text, edits diffed against the baseline, the rewording contradiction (needs an approved prompt or schema change and a v4), registers above ~60 tests.
Not done for lack of time: items 6 and 7 of the priority list (by decision).

## Honest limitations of this assessment
- **The LLM evaluation of the final application is partial.** 15 of 32 planned runs answered: both free tiers ran out (Groq 200,000 tokens per day, Gemini 429). Missing: S2, S5, N1 and most repeats and perturbations.
  Results are indicative; **a new run on a fresh quota is needed** (`uv run python eval/assess_run.py`, about 105,000 Groq tokens).
- On the 156 judgments that exist: 0 missed impacts; 5 wrong cells, all over-flags, 3 with high confidence on critical cells; the LLM beats the rule-only baseline clearly on S1-S10 critical cells (26/27 vs 22/32) and not demonstrably on N1-N6 (5-6/7 vs 6/9, wide intervals).
- Labels for S8-S10 and N1-N6 were written by the assistant (N1-N6 reviewed by the owner), one register, one annotator.
- Not verified: Windows (README commands untested), Docker with a live key, a real browser, real Word-saved tracked-change and encrypted files, duplicate clicks during a run, a 200-test register, why Gemini answered 429, live flows F4-F7 after the fixes.
- After the fixes only flows F1 and F3 (and F2 via the fallback) were re-run live.

## Final checklist against the brief
| Item | Status |
|---|---|
| Application shows changes between spec versions, incl. non-requirement changes | Done |
| Shows affected tests with a readable explanation per test, including not affected | Done |
| Further change by edit or upload with updated result in the UI | Done (live needs quota; edits are diffed against the baseline) |
| LLM is a meaningful part of the analysis | Done (evidence in `01`, `04`) |
| Exportable impact report from the UI (HTML and Markdown) | Done |
| Readable without reading code | Partial (judged from screenshots only) |
| Recommendations, never approval | Done (0 hits in all stored output; detector has known gaps) |
| README: what it does, install/run, safe model config, reproduce, assumptions, sample report | Done (clean-clone verified) |
| Exact commands for Windows or a container | Done for Docker (built and run here); Windows commands **not verified** |
| Screenshot or demo and committed example report | Done (screenshots predate the last fixes; example report regenerated) |
| Input files in the repository | Done |
| No secrets or real data | Done (key values and patterns not in tree or history; one local path in frozen result files, F-006) |
| Working read-only share link to the AI conversation | **Pending, owner's responsibility** (link in README, not opened) |
| License | **Pending, owner's decision** (no LICENSE file) |
| Demo script for the interview | Done (`docs/demo_script.md`) |
