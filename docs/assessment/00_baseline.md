# Phase 0: baseline

Recorded 2026-11-18, before any assessment change.

| Item | Value |
|---|---|
| Commit | `a3ceb64155eaea7b4c795bc41bf5aa26105f62b9` (branch `main`, 25 commits) |
| `git status` | clean (no output) |
| Tests | `uv run pytest -q`: **48 passed** in 21 s (offline, no key) |
| Lint | `ruff check .`: all checks passed; `ruff format --check .`: 44 files already formatted |
| Streamlit | 1.67.0; `streamlit.testing.v1.AppTest` is importable, so UI flows can be scripted |
| Docker | 29.10.0 available (to be used in phase 6) |

## How the app starts

```bash
uv sync
uv run streamlit run app/streamlit_app.py      # http://localhost:8501
# CLI (no UI): uv run vcu-impact analyze --mode replay --report out.md
```
(`make install` / `make run` wrap the same commands; Docker: see README.)

## Replay mode with no key

Verified with `LLM_PROVIDER` empty:
- Streamlit starts headless, `/_stcore/health` returns `ok`.
- `AppTest` loads the page with no exception; tabs: "1 · What changed", "2 · Affected tests", "3 · Edit and re-analyse", "4 · Report"; the first change shown is VCU-DR-01 (100 milliseconds -> 80 milliseconds).
- CLI `analyze --mode replay` prints the per-test table and writes a report.
- Observation to follow up in phase 1: with no provider the "Re-run analysis with the LLM" button reported `disabled=False` in AppTest (the README says it is disabled). Not yet judged.

## Modules

| Module | Role |
|---|---|
| `src/vcu_impact/spec_parser.py` | Word spec -> requirements (ID, title, text) and non-requirement sections |
| `src/vcu_impact/register_parser.py` | Excel register -> tests (with linked requirement IDs) and workshop notes |
| `src/vcu_impact/diff.py` | Deterministic requirement-level diff: added/removed/modified, word-level diff, numeric changes |
| `src/vcu_impact/prompt.py` | System prompt (v3, frozen) and user prompt construction |
| `src/vcu_impact/llm.py` | Provider-agnostic OpenAI-compatible client, structured output validation, retry, fallback |
| `src/vcu_impact/analysis.py` | Runs the LLM assessment; deterministic post-checks (fix_link from register links, rewording safety net) recorded as adjustments |
| `src/vcu_impact/cache.py` | Recorded analyses keyed by exact LLM input (live cache and committed replay files) |
| `src/vcu_impact/pipeline.py` | Input files -> per-test impact view; shared by UI, CLI, report |
| `src/vcu_impact/models.py` | Pydantic models (incl. frozen `LLMImpactResult`) |
| `src/vcu_impact/spec_editor.py` | Applies small edits (number, reword, add, remove) to a .docx for the "try a further change" tab |
| `src/vcu_impact/report.py` | HTML and Markdown report from the same rows as the UI |
| `src/vcu_impact/cli.py` | `vcu-impact analyze` entry point |
| `app/streamlit_app.py`, `app/components.py` | Streamlit UI (four tabs) and display helpers |
| `eval/evaluate.py`, `make_replay.py`, `smoke.py` | Evaluation harness (scenarios S1-S10, scoring views raw / post-check), replay-file builder, smoke test |
| `data/input`, `data/replay` | Provided inputs; committed recorded analyses |
| `tests/` | test_core, test_pipeline, test_report, test_app, test_eval_scoring |
