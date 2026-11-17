# Implementation plan

Approved on 2026-11-17. Model and prompt choice: see [llm_evaluation.md](llm_evaluation.md)
and [known_issues.md](known_issues.md).

## Principles
- **Framework-independent core.** Parsing, diff, LLM, caching and report live in
  `src/vcu_impact/`; the Streamlit app only renders. A CLI uses the same pipeline.
- **The LLM runs only when the user asks.** Edits update the diff immediately; the
  (slow, rate-limited) analysis runs on "Analyse".
- **Every result states its source:** live (model X), replayed (recorded run of model X
  on date D), or not analysed. Nothing is invented.

## Structure
```
src/vcu_impact/  models, spec_parser, register_parser, diff, spec_editor, llm, prompt,
                 analysis (existing) + pipeline, cache, report, templates/, cli (new)
app/             streamlit_app.py, components.py
data/input/      provided files
data/replay/     committed recorded LLM runs (JSON), keyed by input hash
reports/         example exported report (.html, .md)
eval/            evaluation harness (not part of the app)
tests/           unit, pipeline, cache, report, UI smoke tests (offline)
```

## Data flow
Inputs (baseline, revised + UI edits, register) → parsers → diff → cache key
(prompt version + LLM input). Then one of three paths: replay hit, live LLM call (with
post-checks), or deterministic facts only. The result is a per-test view model used by
both the UI and the report.

## Decisions
| Topic | Decision |
|---|---|
| UI | Streamlit; tabs Changes / Impact / Edit / Report; sidebar for inputs and model |
| Model | Prompt v3, Groq `qwen/qwen3.8-27b`; optional fallback Gemini `gemini-3.5-flash` |
| Replay | Prompt v3 evaluation runs (7 scenarios) committed as replay recordings |
| Report | HTML (self-contained, printable to PDF from the browser) and Markdown; no PDF library |
| Screenshots | Taken manually by the project owner; no screenshot tooling in the code |
| Docker | Dockerfile written during implementation; tested once Docker is installed |
| Git | Commit per milestone; **no push until step 4 is verified** by the project owner |

## Milestones
1. **M1:** pipeline, cache, CLI, replay recordings from the v3 evaluation runs.
2. **M2:** read-only UI: sidebar, Changes tab, Impact tab with detail panel.
3. **M3:** edits, uploads, live analysis, fallback.
4. **M4:** report (HTML and Markdown), Report tab, example report in `reports/`.
5. **M5:** Makefile, Dockerfile, README, final secrets check.
