# VCU-42 Spec Change Impact Analyzer

AI-assisted impact analysis for a fictional vehicle controller (VCU-42): compare two
specification revisions, find the existing tests that may be affected, review the LLM's
explanation, and export an engineering impact summary.

- **What changed:** requirement-level diff of two Word specifications, with word-level
  highlighting and numeric changes (e.g. `100 milliseconds → 80 milliseconds`).
- **Which tests may be affected, and why:** every test in the Excel register gets a
  status, a confidence, required actions (re-run, update procedure, fix link, owner
  decision) and a short evidence-based reason, including tests judged *not affected*.
- **Try a further change:** edit, add or remove a requirement in the browser, or upload
  other files, then re-run the analysis.
- **Export:** an HTML or Markdown engineering impact report from the UI or the CLI.

The register is treated as **evidence, not approval**. The application gives
recommendations; final approval belongs to the authorized owner.

> **Sample report:** [reports/example_impact_report.html](reports/example_impact_report.html)
> (also as [Markdown](reports/example_impact_report.md)), generated from the provided files.

<!-- TODO(owner): add the screenshots, e.g. docs/screenshots/changes.png and impact.png -->
**Screenshots:** _to be added in `docs/screenshots/`._

## Quick start

Requirements: [uv](https://docs.astral.sh/uv/) (it installs Python 3.12 if needed). No API
key is needed to try the application: without one, it shows **recorded** LLM analyses
(see [What is live and what is replayed](#what-is-live-and-what-is-replayed)).

### Ubuntu / WSL / macOS

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh     # once; then open a new terminal
git clone <repository-url> vcu-impact-analyzer && cd vcu-impact-analyzer
make install    # uv sync + creates .env from .env.example
make run        # http://localhost:8501
```

Without `make`: `uv sync`, `cp .env.example .env`, `uv run streamlit run app/streamlit_app.py`.

### Windows (PowerShell)

```powershell
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"   # once; then open a new terminal
git clone <repository-url> vcu-impact-analyzer; cd vcu-impact-analyzer
uv sync
Copy-Item .env.example .env
uv run streamlit run app/streamlit_app.py
```

> **Not verified on native Windows.** Development and testing were done on Ubuntu 24.04
> (WSL2). The code uses only cross-platform Python packages and `pathlib`, but these
> PowerShell commands have not been run on a Windows machine.

### Docker

```bash
docker build -t vcu-impact .
docker run --rm -p 8501:8501 vcu-impact                    # replay mode, no key
docker run --rm -p 8501:8501 --env-file .env vcu-impact    # with a live model
```

Then open http://localhost:8501. `make docker-build` and `make docker-run` do the same.
The image never contains `.env` (excluded by `.dockerignore`); keys are passed at run time.

> **Docker status (verified on Ubuntu 24.04 / WSL2, Docker 29.10):** the image builds; the container
> starts, reports healthy, runs as a non-root user and contains no `.env`; replay mode works
> without any key; a live analysis works with `--env-file .env`. **Not verified:** Docker
> Desktop on native Windows or macOS.

## Model configuration (safe)

Configuration is read from environment variables, loaded from a local `.env` file that is
**git-ignored and never committed**. Only the template `.env.example` is in the
repository. Keys are never printed, logged or written to reports; the UI only shows
whether a model is configured.

```bash
cp .env.example .env      # then edit .env and add your key(s)
```

| Variable | Purpose | Default in `.env.example` |
|---|---|---|
| `LLM_PROVIDER` | `groq`, `gemini`, `cerebras`, `mistral`, `ollama` or `openai_compatible` | `groq` |
| `LLM_MODEL` | Model ID at that provider | `qwen/qwen3.8-27b` |
| `LLM_BASE_URL` | Optional endpoint override (required for `openai_compatible`) | empty |
| `LLM_API_KEY` | Optional; if empty, the provider's own variable is used | empty |
| `GROQ_API_KEY`, `GEMINI_API_KEY`, … | Provider keys | empty |
| `LLM_FALLBACK_PROVIDER`, `LLM_FALLBACK_MODEL` | Optional second model, used once if the first fails (rate limit, outage) | `gemini`, `gemini-3.5-flash` |
| `LLM_TIMEOUT_S`, `LLM_MAX_TOKENS` | Optional tuning | `600`, `16384` |

Free keys: Groq at https://console.groq.com/keys, Google AI Studio at
https://aistudio.google.com/apikey. A local model also works:
`ollama pull qwen3:8b`, then `LLM_PROVIDER=ollama`, `LLM_MODEL=qwen3:8b` and
`LLM_TIMEOUT_S=1800` (much slower and less accurate, see the evaluation).

**Why this model:** five models were compared on a task-specific dataset (7 change scenarios,
84 hand-labelled judgments), then the prompt was re-run on the three best candidates with three
extra held-out scenarios. This is a **smoke test, not a ranking**: most labelled cells are easy,
there is one annotator and one register. What it supports: gpt-oss-120b is clearly weaker for this
task, and Groq `qwen/qwen3.8-27b` and Gemini 3.5 Flash cannot be told apart on accuracy (a tie).
qwen is the primary model because ties go to it by a rule fixed before the follow-up runs, and
because it answers in about 7 s against about 95 s, which makes live re-analysis practical.
Gemini is the configured fallback. Method, results and caveats are in
[docs/llm_evaluation.md](docs/llm_evaluation.md).

## What is live and what is replayed

Every result in the UI and in the report states its source:

| Label | Meaning |
|---|---|
| **Live** | The configured model was called now, for exactly these inputs. |
| **Replayed** | Real output of `groq:qwen/qwen3.8-27b`, recorded on 2026-11-16 during the evaluation and committed in [`data/replay/`](data/replay/). No model is called. |
| **Cached** | An earlier live run in this environment (`.cache/`, git-ignored). |
| **Not analysed** | No recording exists and no model is configured or available. The diff and the parsed register facts are still shown; no assessment is invented. |

Recordings exist for the provided files (the real revision B) and for the six evaluation
scenarios in [`eval/scenarios/`](eval/scenarios/) (upload one as the revised spec to see
it). Any other edit needs a configured model. Recordings are matched on a hash of the
exact model input (prompt version, prompt text, parsed changes and register), so a
recording is never shown for inputs it was not made for. Deterministic post-checks are
re-applied to recordings when they are loaded.

## How to reproduce a result

```bash
# The provided files, from the recorded analysis (no key):
uv run vcu-impact analyze --mode replay
# Same, and regenerate the committed example report:
make report
# A change of your own, with a live model (needs a key in .env):
uv run vcu-impact analyze --revised path/to/your_spec.docx --mode live --report out/report.html
# The LLM evaluation tables, from the stored runs:
make eval-score
```

In the UI: open **3 · Edit and re-analyse**, change for example `within 80 milliseconds`
to `within 90 milliseconds` in VCU-DR-01 and apply. Tab 1 shows the new diff; then click
**Run analysis with the LLM** in the sidebar. **4 · Report** downloads the result.

## How it works

```
baseline.docx ─┐                                   ┌─ replay: recorded run
revised.docx ──┼─ parse ─► diff ─► LLM input ─► key ┼─ live: LLM (strict JSON schema) ─► post-checks
register.xlsx ─┘  (code)   (code)                   └─ none: facts only
                                       │
                         per-test rows ─► UI tabs + HTML/Markdown report
```

| Done by code (deterministic) | Done by the LLM (judgment) |
|---|---|
| Parse requirements by ID pattern; diff requirements, titles, numbers and other sections | Interpret each change (tightened, relaxed, reworded, …) and what it means for verification |
| Parse the register; classify each link as valid, missing, TBD, unknown or removed | Judge every test's relevance, **including tests with no valid link** |
| Extract values from free-text results (e.g. `PASS (94 ms)` → 94 ms) | Compare evidence with the new requirement: same quantity, same clock (workshop notes) |
| Set `fix_link` for every broken link | Decide re-run vs procedure update vs owner decision; write the reason and evidence |
| Validate the output: all tests covered, no invented IDs, no approval wording; correct one known self-contradiction (below) | |

The LLM output is a strict JSON schema validated with Pydantic, with one automatic
repair retry. The UI and the report are built only from validated data.

## Assumptions

- **Specification format:** a requirement starts with a short paragraph beginning with an
  ID such as `VCU-DR-01` (upper-case parts separated by `-`, ending in a number),
  optionally followed by a title. Its text runs until the next requirement or heading.
  Styling is not used, so files re-saved in Word still parse. Duplicate IDs are rejected.
- **The baseline is the reference.** Edits made in the UI apply to the revised
  specification. Requirements are matched by ID; a renamed ID counts as removed plus added.
- **Register format:** the header row is found by column names (`Test case`,
  `Req reference`, `Result`, …) in the first 20 rows, so title rows above it are fine. The
  workshop notes are read from any sheet with `Date` and `Observation` columns. Links may
  list several IDs separated by `;`, `,` or `/`.
- **Broken links:** an empty cell, `TBD`/`TBC`/`N/A`, an ID found in neither
  specification (e.g. `VCU-OLD-88`) or an ID removed in the revision are broken links:
  they always get `fix_link`, and are never taken as proof that a test is unrelated.
- **Evidence, not approval:** a previous `PASS` is evidence from an earlier campaign that
  may not cover a newer requirement. Reports never state approval; a post-check flags
  approval-like wording.
- **Workshop notes are context for the LLM**, not hard-coded rules (e.g. brake and torque
  latency are measured on different clocks).
- **Only requirement changes trigger an assessment.** Other changed sections (e.g.
  revision notes) are shown and passed to the model as context. If no requirement
  changed, no model is called.
- **Scale:** evaluated on registers of 12 tests (13 in one held-out scenario). The UI warns above 60 tests; larger
  registers would need batching (not implemented).
- **Single local user:** no authentication, no database; state lives in the browser
  session, live results are cached in `.cache/`. The register can be replaced by upload
  but not edited in the app.
- **Fictional data only.** Recorded analyses and reports contain only the provided
  fictional material.

## Known issues and limitations

See [docs/known_issues.md](docs/known_issues.md). The most important one: the model can
mark a test *directly affected* for a **pure rewording** of a requirement although its own
interpretation of the change says nothing changed. This is a safety net in the application,
not an improvement of the model: the post-check changes that status to *not affected* and
shows the change next to the test (the original model output is kept). It relies on the
model's reading of the change, which is not evaluated and not stable, so it never fires when
the diff found a changed number in that requirement; a wrong "rewording" on a change without
numbers could still hide a real impact. The rule is not validated (it was written after seeing
the failure it fixes).

The evaluation is small (84 judgments, one register, one annotator), and the prompt was
refined on the same scenarios. Free-tier latency, rate limits and availability can change
without notice.

## Tests

```bash
make test     # 45 offline tests: parsing, diff, editing, post-checks, pipeline, cache, report, UI smoke
make lint
```

The tests need no network and no key. LLM quality is measured separately by the
evaluation harness in [`eval/`](eval/), which needs keys.

## Repository layout

| Path | Content |
| --- | --- |
| `data/input/` | Provided exercise inputs (baseline spec, revised spec, test register) |
| `data/replay/` | Recorded LLM analyses used in replay mode |
| `src/vcu_impact/` | Core: parsers, diff, editor, LLM client, prompt, analysis, pipeline, cache, report, CLI |
| `app/` | Streamlit UI |
| `reports/` | Example exported report |
| `eval/` | LLM evaluation: dataset, scenarios, harness, stored runs, frozen prompts |
| `docs/` | Evaluation report, known issues, implementation plan, original exercise brief |
| `tests/` | Offline test suite |
| `.env.example` | Template for LLM configuration |

## AI conversations

<!-- TODO(owner): add the read-only share links before submitting (mandatory). -->
_Share links to the AI conversations used for this exercise: to be added._
