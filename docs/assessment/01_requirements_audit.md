# Phase 1: requirements audit

Method: the brief (`docs/exercise_brief.docx`) was extracted line by line; the application was driven through the real
Streamlit UI with `streamlit.testing.v1.AppTest` (script: `eval/ui_flows.py`, results in `docs/assessment/results/`),
in replay mode (no key) and in live mode (Groq qwen3.8-27b primary, Gemini 3.5 Flash fallback, free tiers).
Not done: a real browser session (no browser tooling, by the owner's preference); visual judgements below come from the
four committed screenshots and from the rendered element tree, so they are **partly not verified**.

## Traceability table

| # | Brief item | Evidence | Status | Findings |
|---|---|---|---|---|
| B1 | Small working app to explore what changes between two spec versions | UI tab "1 · What changed"; flow F0 (replay) shows VCU-DR-01 modified, 100 -> 80 ms | Met | |
| B2 | ...including non-requirement changes | `diff.section_changes` shown in expander "Other document changes" (revision label, notes) | Met (tested only on the provided pair; Word-specific cases in phase 3) | |
| B3 | See which existing tests may be affected, with an explanation | Tab 2: 12 tests, status, confidence, actions, reason, evidence, also for "not affected" (flow outputs; screenshot 12234) | Met | F-007 |
| B4 | Make or upload a further small change; updated result in the UI | Flows F1-F7 below | Met with caveats | F-002, F-004 |
| B5 | LLM is a meaningful part of the analysis | `analysis.run_analysis` sends diff + parsed register + notes; the model returns per-test status/actions/reason and per-change interpretation. Evidence it is not a restatement: TV-003 has **no requirement link** and is still flagged directly/possibly affected from its content (92 ms result, 75-95 % demand) in every live flow; a link-only baseline cannot do that. Code-only parts: diff, link parsing, `fix_link`, post-check | Met | |
| B6 | Clear visual experience; reviewer understands without reading code | Screenshots; see "First-time user" below | Partial (not verified in a browser) | F-009 |
| B7 | Exportable engineering impact summary, accessible from the interface | Tab 4: HTML + Markdown download, preview. In all 7 live flows the report contained every test ID and every status label shown in the table | Met | |
| B8 | Provided material used (3 files) | `data/input/`, default load | Met | |
| B9 | Repo with source, assets, input files | 193 tracked files; inputs under `data/input/` | Met | |
| B10 | README: what it does, start, safe model config, reproduce, review sample report | README sections present (quick start, model configuration, reproduce, assumptions, limitations, AI conversations) | Met, to be re-verified from a clean clone in phase 6 | F-008 |
| B11 | Exact commands for Windows **or** container | Docker and PowerShell commands in README | Partial: Docker not yet built here, Windows not verified (README says so) | phase 6 |
| B12 | At least one screenshot or demo + committed example report | `docs/screenshots/` (4 JPEG), `reports/example_impact_report.{html,md}`; regenerating the Markdown from replay reproduces it except the timestamp | Met | |
| B13 | Working read-only share link to the AI conversation | README "AI conversations" lists a claude.ai share URL | **Not verifiable** (owner's responsibility; link not opened) | |
| B14 | No secrets / client data / personal info in repo, reports, conversations | Scan below | Met for secrets; Partial for personal info | F-006 |
| B15 | Model access documented via env vars, never committed | `.env.example`, `.env` git-ignored, keys not in history | Met | |
| B16 | State assumptions in the README | README "Assumptions" | Met | |
| B17 | Ready to demo a small change not in the original files | Flows F1-F7 | Met, but 4 of 7 live runs fell back to the secondary model | F-002 |
| B18 | Recommendations, never claim approval (task requirement, from the spec's "evidence is not approval") | Scan below | Met in all stored output; detector has gaps | F-005 |

## Demo flows through the UI

Replay mode, no key: every edit produces the correct updated diff and a clear warning "Not analysed by an LLM ... no recorded
analysis" (no crash, no stale result shown). Live mode, results (`results/ui_flows_live.json`):

| Flow | Change | Diff shown | Live result | Model used | Time |
|---|---|---|---|---|---|
| F1 | DR-01 80 -> 60 ms | DR-01 modified (100 -> 60) | TV-001 directly, TV-003 directly/medium, TV-002 possibly | Groq | 5.7 s |
| F2 | reword DR-02 | DR-01 + DR-02 modified | DR-02 read as `reworded_same_meaning`; TV-010 not affected (correct) | Gemini (Groq 429) | 66 s |
| F3 | add VCU-THM-07 | DR-01 modified, THM-07 added | interpretation `added`; no test wrongly tied to it | Groq | 11.5 s |
| F4 | remove VCU-LOG-05 | DR-01 modified, LOG-05 removed | TV-006 directly affected, actions fix_link + owner_decision (sensible) | Gemini (Groq 429) | 51 s |
| F5 | DGN-04 adds "and the vehicle is moving" | DR-01, DGN-04 modified | `scope_changed`; TV-005 directly/high (correct) | Groq | 5.8 s |
| F6 | upload revised spec, BRK-03 loses "or requested driving mode" | DR-01, BRK-03 modified | Gemini read it as `reworded_same_meaning` (debatable), TV-002 directly/high, TV-009 not affected/high | Gemini (Groq 429) | 44 s |
| F7 | upload register, TV-003 linked to DR-01 | DR-01 modified; sidebar "12 tests" | TV-003 directly/high; analysis ran, no exception | Gemini (Groq 429) | 54 s |

No exception in any flow; the banner always states live vs replay and, when the fallback was used, why.

## Secrets and personal data scan

- Exact values of the two keys in `.env` (Groq, Gemini): not found in the working tree or in any commit of any branch.
- Patterns (`gsk_`, `AIza`, `sk-`, `csk-`, bearer tokens, `api_key=` assignments): 0 hits in the tree, 0 in history. No tracked `.env`, key or certificate file. E-mail addresses: none.
- Found: 8 tracked files under `eval/results/v1/gemini-3.5-flash-lite/` contain Python tracebacks with the absolute local path `/home/cberti/...` (F-006). The provided .docx/.xlsx carry the author "Autonomous Reply France": that comes from the brief's own material.
- Found during this audit (not committed): provider error text includes an organisation id (F-003); the assessment result files redact it.

## Approval language

The existing detector (`analysis.approval_language`) was run over 10,484 strings in 110 JSON files (all replay recordings and all
`eval/results`, excluding raw text), the example reports, README and `docs/llm_evaluation.md`: **0 hits**. The reports contain
only the negated disclaimer. Read by eye: the reasons and recommended actions of the 7 live runs say "re-run", "update procedure",
"owner decision"; none claims acceptance. **But** the detector is weak on adversarial wording (F-005): of 22 test phrases it missed
"The owner approved the change", "It was never approved, but is approved now", "approval is granted", "accepted", "authorised",
"ready for release", "cleared for release", "verified and compliant". It is a warning only, and it scans test assessments,
not `engineering_summary`.

## First-time-user judgement (from screenshots and element tree)

Good: four numbered tabs in work order; coloured status with plain words; summary counts; filters; a banner that says live /
replayed / not analysed; a standing line "evidence, not approval"; the "from the model" vs "from the register data" split in the detail
panel. Weaker: the `*` marker for code-set actions is explained only in a caption under the table; "confidence" is not explained;
"Re-run analysis with the LLM" next to a banner "Replayed" is understandable only after reading it; after an edit the diff lists the
original DR-01 change together with the new one (F-004). Severity S4 unless noted.

## Findings from this phase

| ID | Sev | Finding | Evidence |
|---|---|---|---|
| F-001 | S2 | The numeric diff is not unit-aware: `100 ms -> 0.1 s` and `100 ms -> 0.10 seconds` are reported as two unrelated changes (old value removed, new value added) instead of "equivalent" or "-> 0.1 s = 100 ms"; `1,5 s -> 1.5 s` is correctly equal; `100 ms -> 100 milliseconds` correctly equal; the number inside an ID in running text (`VCU-DR-01 -> VCU-DR-02`) is reported as a numeric change `01 -> 02` (hidden in the UI because it has no unit, still in the prompt data) | direct calls to `diff.numeric_changes` |
| F-002 | S2 | Live reliability on the free tier: Groq returned 429 (output-tokens-per-minute limit 1000) for 4 of 7 consecutive live runs; each fell back to Gemini and took 40-66 s instead of 5-12 s. The SDK retry does not wait out the window. The 429 text is cut at 200 characters in the banner so the cause is hard to read. A demo with several changes in a row will mostly run on the fallback | `results/ui_flows_live.json` |
| F-003 | S3 | Provider error text (including the Groq organisation id) is copied into the UI banner, the local cache and the exported report (`pipeline._live` notes -> `run.warnings` -> report global warnings) | `.cache/analyses/*` warnings |
| F-004 | S3 | Edits are applied to the revised file and diffed against the **baseline**, so every flow still shows the original DR-01 change and its test impacts; the user cannot see what their own edit changed (no before/after comparison of the assessment) | all flows list DR-01 |
| F-005 | S3 | Approval detector: misses several approval phrasings and negation heuristic can hide a claim ("owner approved"); scans only test assessments | direct calls |
| F-006 | S3 | Local absolute path (`/home/cberti/...`) in 8 committed frozen result files | `git grep` |
| F-007 | S2 | Model-dependent change reading: in F6 Gemini called the removal of "regardless of ... requested driving mode" `reworded_same_meaning` and marked TV-009 / TV-011 not affected with high confidence; the label is debatable (VCU-MOD-06 still says mode must not change the brake priority), so this is recorded as contested, not as a proven miss. To be scored in phase 4 | live cache |
| F-008 | S4 | README has a TODO comment and a vague screenshot sentence (line 22), `<repository-url>` placeholders, no LICENSE file (decision for the owner) | README |
| F-009 | S4 | No real-browser check of layout, and the `*`/confidence explanations are thin (see above) | screenshots |

Counts: S1 0, S2 3, S3 4, S4 2 (no brief violation found; deliverables B11 and B13 remain open).
