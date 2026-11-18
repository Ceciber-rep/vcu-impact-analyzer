# Phase 5: improvements

Approved scope: items 1-5 and 8 of the priority list; items 6 and 7 documented as limitations only. Frozen items untouched (v3 prompt, LLM schema,
model choice, `eval/results/v1-v3`; no v4 was created). For each fix a failing test existed before the change (the strict `xfail` from phase 3); the
fix turns it into a normal test. Full suite after the last change: **113 passed, 21 xfailed** (the 21 are the documented, unfixed findings), lint clean.

| Finding | Commit | Before | After |
|---|---|---|---|
| F-010 (S1) tracked changes ignored | "Fix F-010" | `<w:del>100 ms</w:del><w:ins>80 ms</w:ins>` parsed as "The value is" (both numbers lost, no warning) | insertions kept, deletions dropped; the UI and the report say "contains tracked changes ... read as if all were accepted" (E-014, E-015) |
| F-020 (S2) refresh hides a live result | "Fix F-020" | after a refresh the sidebar says "Run" although the result is on disk; a click re-calls the provider | the saved result is shown again as "From an earlier live run", 0 provider calls (E-072) |
| F-023 (S2) hour-long hang | "Fix F-002/F-003/F-022/F-023" | request timeout 600 s, 2 SDK retries, no overall limit (one failure took 3,618 s) | 90 s per request, 1 retry, 240 s per provider (`LLM_TIMEOUT_S`, `LLM_TOTAL_TIMEOUT_S`); worst case about 8 minutes with fallback (E-044b) |
| F-022 (S2) / F-002 / F-003 provider limits | same | banner "RateLimitError: Error code: 429 - Request too large ... organization `org_...`" cut at 200 characters | "daily token limit of the free tier reached; try again later or use the recorded analysis", "per-minute rate limit ...", "the API key was rejected", no organisation id, plus "The changes and register facts are still shown" (E-042, E-042b). The limit itself cannot be removed on a free tier |
| F-016 (S2) several IDs in a link cell | "Fix F-015/F-016" | `VCU-A-01\nVCU-B-02` kept only the first | all IDs kept for newline, space and "and" separators (E-028) |
| F-015 (S2) duplicate test IDs | same | accepted silently | clear error naming the ID (E-026) |
| F-001 (S2) units | "Fix F-001" | `100 ms` vs `0.1 s` reported as two changes; `01 -> 02` from an ID in the text | seconds compared as milliseconds (and kHz as Hz); numbers inside IDs ignored; `100 ms -> 0.08 s` is still a change 100 -> 80 (E-011, E-011b, E-013). Scenario N1 now has no numeric change |
| F-025 (S3) confidence | "Fix F-025" | no caveat | one-line note under the results table and a limitation in the report |

## Verification after the last change

- `uv run pytest`: 113 passed, 21 xfailed; `ruff check` and `ruff format --check` clean.
- UI flows F0-F7 in replay mode: no exception, report contains every test (same as before the changes).
- Live smoke test, flow F1 (DR-01 to 60 ms) through the UI with the primary model: answered by Groq in 6.8 s, 12 statuses shown.
  Only this one live flow was re-run (free-tier quota); flows F2-F7 were **not** re-run live after the fixes.
- The committed replay recordings still match their inputs (`test_every_scenario_has_a_committed_recording` passes), so the prompt text for the
  committed scenarios did not change. The prompt for inputs with unit conversions or IDs inside requirement text does change slightly (the numeric hint); the
  prompt template, schema and post-check were not changed, so phase 4 numbers remain comparable for the scenarios that ran, but any re-run should state the code version.

## Documented, not fixed (limitations)

F-011 (text boxes and tables), F-012 (unrecognised ID formats), F-013 (raw upload error messages), F-014 (merged cells, formulas without cached values), F-017 (lower-case IDs in link cells),
F-005 (approval detector gaps, plus `engineering_summary` is not scanned), F-018 (markdown rendered from untrusted text), F-021 (duplicate clicks), F-004 (edits are diffed against the baseline),
F-019 (report timestamp), F-024 (rewording contradiction depends on the unscored `nature`; a prompt or schema change needs approval and a v4), F-006 (local path in frozen result files),
F-007 (model-dependent reading of a debatable change), and the incomplete phase 4 run (F-026).

## Ideas parked for later

Show the impact of the user's own edit separately from the original revision (F-004); warn on text boxes, tables and unknown ID formats; a rule that flags
"reason says unchanged, status says directly affected" for any change type; a daily-quota indicator; a result export of the evaluation run; resume and finish the phase 4 plan on a fresh quota.
