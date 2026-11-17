# LLM selection and evaluation

This report documents how the model behind the impact assessment was chosen: the
options considered, the constraints (no paid API key, a laptop without a discrete GPU),
and a small task-specific evaluation run on 2026-11-16. Every number here comes from
the raw outputs stored under [`eval/results/<prompt version>/`](../eval/results/); they can
be re-scored with `uv run python eval/evaluate.py score --version v1` (or `v2`, `v3`).

**Reading guide.** Sections 1–6 describe the model comparison, run with prompt **v1**
(status only). Section 7 describes the later `required_actions` field, which produced prompts
v2 and v3, and was run on the recommended model only.

## 1. What the model has to do

For one specification change, the model reads the deterministic facts produced by the
code (the requirement diff, the parsed links with their validity, values extracted from
the free-text results) together with the raw register text and the workshop notes. It
then returns, as JSON validated against a strict schema, a status, a confidence, a
reason, evidence and a recommended action for every test.

- Input is about 4,000 tokens; output is 2,000–4,000 tokens (more for reasoning models).
- The context is small, so the difficulty lies in the reasoning. The model must:
  - notice that TV-003 (no link) measures the same torque response that changed;
  - not compare a brake latency of 88 ms on another clock with an 80 ms torque limit (TV-004);
  - not confuse "80% pedal" with "80 ms" (TV-007);
  - understand that a relaxed limit keeps old evidence valid;
  - never phrase a recommendation as approval.
- The output must be schema-valid every time, because the UI and the report are built from it.

## 2. Constraints and hardware

| Item | Value | Consequence |
|---|---|---|
| Budget | No paid API key | Only free tiers or local models |
| CPU | AMD Ryzen AI 7 PRO 360, 8 cores / 16 threads, AVX-512 | Workable for CPU inference of small models |
| RAM | 31 GB host, 15 GiB visible to WSL2 (default cap) | Models up to about 8B parameters without changing WSL settings |
| GPU | Radeon 880M integrated, no NVIDIA | Ollama under WSL2 runs CPU-only |
| OS | Ubuntu 24.04 on WSL2 | The reviewer may be on Windows or use Docker |

Commands used to check the hardware (Ubuntu):

```bash
lscpu | grep -E 'Model name|^CPU\(s\)'
grep -o -m1 'avx512f\|avx2' /proc/cpuinfo
free -h
df -h ~
nvidia-smi || lspci | grep -iE 'vga|3d'
powershell.exe -c "(Get-CimInstance Win32_ComputerSystem).TotalPhysicalMemory/1GB"   # WSL only
```

## 3. Options considered

The table summarises the analysis made before any test. The latency column holds the
*expected* figures from that analysis; measured figures are in section 5.

| Option | Cost | Setup effort | Expected latency per analysis | Expected quality | Structured output | Hardware | Reproducible by a reviewer |
|---|---|---|---|---|---|---|---|
| Ollama, small dense model (`qwen3:8b`, 5 GB) | Free | About 15 min + 5 GB download | 3–6 min (CPU) | Moderate; small models are the most exposed to the number traps | Grammar-constrained JSON schema | Fits in 15 GiB | Poor: install Ollama and download 5 GB |
| Ollama, MoE model (`gpt-oss:20b`, `qwen3:30b-a3b`) | Free | About 30 min + 13–19 GB, raise WSL memory cap | 2–5 min | Good | Grammar-constrained | Needs about 24 GB for WSL | Poor |
| GitHub Models | Free, rate-limited | 5 min (token) | 10–40 s | High | Strict JSON schema | None | Good (every reviewer has a GitHub account) |
| Google Gemini API, free tier | Free, rate-limited | 5 min (key) | 10–30 s | High | Native schema | None | Medium (needs a Google key) |
| Groq / Cerebras / Mistral free tiers | Free, rate-limited | 5 min (Mistral asks for phone verification) | 3–20 s | High (70–120B models) | Good | None | Medium |
| OpenRouter `:free` models | Free | 5 min | Variable | Variable | Depends on upstream | None | Low (models come and go) |
| Replay of a recorded run | Free | None | Instant | Same as the recorded model | Already validated | None | Excellent, but only for inputs already analysed |

Two design decisions followed from this analysis, independently of the final model:

1. **One provider-agnostic client.** Every hosted option exposes an OpenAI-compatible
   API, so switching provider is configuration only (`LLM_PROVIDER`, `LLM_MODEL`,
   `LLM_BASE_URL`, `LLM_API_KEY`). Ollama is called through its native API, which is the
   only way to set the context window (its default is too small for this prompt).
2. **Replay for reviewers.** Whatever model is chosen, the application ships real
   recorded outputs, keyed by the input content and labelled as replayed in the UI. That
   way a reviewer without credentials still sees genuine LLM output, and a live model is
   only needed for new edits.

### What changed when the options were tested

- **GitHub Models was retired on 2026-07-30** ([GitHub docs](https://docs.github.com/en/github-models/quickstart)).
  The endpoint `models.github.ai` now answers `200 OK` (plain text) to every request,
  authenticated or not. It had been the initial recommendation (strict schema, and a
  reviewer could use their own GitHub account); that recommendation came from outdated
  knowledge and was dropped after the smoke test.
- **Cerebras and Mistral** were not tested: the account owner reported that both
  required a paid account at sign-up. This was not independently verified.
- **Gemini:** `gemini-2.5-flash` returned 404 (no longer served), and
  `gemini-flash-latest` and `gemini-3.8-flash` timed out after 90–150 s on a one-word
  prompt. `gemini-3.5-flash` took about 40 s even for a one-word reply, which looks like
  free-tier queueing rather than model work. `gemini-3.5-flash-lite` answered in 1–3 s.

## 4. Evaluation method

### Why a custom dataset

Public benchmarks (IFEval, JSONSchemaBench, MMLU…) measure general instruction following
and knowledge, and published scores already exist for most models. They do not tell us
whether a model confuses brake latency with torque latency in *this* register. The
evaluation therefore uses a small dataset built from the project's own documents.

### Dataset

[`eval/dataset.yaml`](../eval/dataset.yaml) holds 7 scenarios × 12 tests = **84 labelled
judgments**.

- Each scenario is the baseline specification plus one edit, analysed against the
  original, unmodified register.
- S1 is the real revised specification. S2–S7 are generated from the baseline by
  [`eval/evaluate.py build`](../eval/evaluate.py) and committed under
  [`eval/scenarios/`](../eval/scenarios/).

| # | Change | What it probes |
|---|---|---|
| S1 | DR-01 response time 100 → 80 ms (real revision B) | Baseline case, unlinked TV-003, brake-clock trap TV-004, "80%" trap TV-007 |
| S2 | BRK-03 gains an 80 ms brake latency limit | Reverse clock trap: now TV-004 is affected and TV-001 is not |
| S3 | DR-02 spike filter 10 → 5 ms | Reasoning on a non-latency limit: the 7 ms pulse in TV-010 is no longer filtered |
| S4 | DR-01 relaxed 100 → 120 ms | Over-flagging when a limit is loosened |
| S5 | DGN-04 reworded, same meaning | Over-flagging a cosmetic change |
| S6 | MOD-06 removed | A link that becomes orphaned (TV-009) |
| S7 | New requirement THM-07 (thermal derating) | Added requirement with no existing link (TV-007) |

Labels were written by hand from the documents before any model was run. Ambiguous cases
accept several statuses. Each label has:
- a **preferred** status;
- an **accepted** set of statuses;
- a **critical** flag for the named traps and for cases where a miss would hide a real impact (16 of the 84).

### Protocol

- The same system prompt (frozen in [`eval/prompts/v1/`](../eval/prompts/v1/)), the same input and the same JSON
  schema for every model. Nothing was tuned per model. Temperature 0 where the provider
  accepts it.
- One run per scenario. S1 is run 3 times to measure consistency.
- The application's post-checks are applied, as in production: coverage of all 12
  tests, invented IDs removed, approval wording flagged. A test the model omits is
  scored as wrong.

### Metrics

| Metric | Definition |
|---|---|
| Valid 1st try | Output passed schema validation without the repair retry |
| Lenient accuracy | Status is in the accepted set (84 judgments, first repetition) |
| Strict accuracy | Status equals the preferred label |
| Critical cases | Lenient accuracy on the 16 critical judgments |
| Missed impacts | `not_affected` on a test whose accepted set excludes it; the most serious error |
| Over-flags | `directly_affected` on a test whose accepted set excludes it |
| Approval wording | Approval-like phrases in reasons or actions (regex, negations excluded) |
| S1 consistency | Tests with the same status in all 3 S1 runs |
| Latency | Wall-clock per analysis; for hosted free tiers this includes rate-limit back-off |

### Harness issue found during the run

The first Groq gpt-oss-120b run of S4 hit Groq's default output cap of about 3,000
tokens, which the model's reasoning tokens use up.
- The harness wrongly treated the error as "schema not supported" and fell back to
  JSON mode. The model then returned only 9 of the 12 tests; the post-check marked the
  other 3 `needs_human_review`, as designed.
- The client now sets an explicit output budget (16,384 tokens, doubled once on
  truncation) and only falls back to JSON mode on a genuine schema-support error.
- The affected run was re-run and the original is kept in
  [`eval/results/v1/_superseded/`](../eval/results/v1/_superseded/). Runs that had not hit the
  cap are unaffected by the change, so they were not repeated.

## 5. Results

Run on 2026-11-16 with prompt `v1`. The raw outputs are in
[`eval/results/v1/`](../eval/results/v1/) and this table is generated by
`eval/evaluate.py score --version v1` (also in
[`eval/results/v1/summary.md`](../eval/results/v1/summary.md)).

| Model | Runs ok | Valid 1st try | Lenient acc. | Strict acc. | Critical cases | Missed impacts | Over-flags (D) | Unneeded review flags | Omitted tests | Approval wording | S1 consistency | Median latency | Median output tokens | Service errors |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| gemini-3.5-flash | 9/9 | 100% (9/9) | 96% (81/84) | 85% (71/84) | 88% (14/16) | 0 | 3 | 6 | 0 | 0 | 11/12 over 3 runs | 137 s | 2023 | 0 |
| gemini-3.5-flash-lite | 1/9 | 100% (1/1) | 92% (11/12) | 75% (9/12) | 83% (5/6) | 1 | 0 | 0 | 0 | 0 | n/a | 7 s | 1721 | 10 |
| groq-gpt-oss-120b | 9/9 | 100% (9/9) | 95% (80/84) | 81% (68/84) | 88% (14/16) | 0 | 2 | 6 | 4 | 0 | 9/12 over 3 runs | 46 s | 2697 | 0 |
| groq-qwen3.8-27b | 9/9 | 100% (9/9) | 96% (81/84) | 82% (69/84) | 94% (15/16) | 0 | 1 | 5 | 0 | 0 | 12/12 over 3 runs | 7 s | 1699 | 2 |
| ollama-qwen3-8b | 9/9 | 100% (9/9) | 94% (79/84) | 86% (72/84) | 75% (12/16) | 1 | 4 | 3 | 0 | 0 | 9/12 over 3 runs | 510 s | 3067 | 0 |

Per-scenario lenient score (first repetition):

| Model | S1 | S2 | S3 | S4 | S5 | S6 | S7 |
|---|---|---|---|---|---|---|---|
| gemini-3.5-flash | 12/12 | 12/12 | 12/12 | 10/12 | 12/12 | 12/12 | 11/12 |
| gemini-3.5-flash-lite | 11/12 | failed | failed | failed | failed | failed | failed |
| groq-gpt-oss-120b | 12/12 | 12/12 | 12/12 | 11/12 | 12/12 | 10/12 | 11/12 |
| groq-qwen3.8-27b | 12/12 | 12/12 | 11/12 | 11/12 | 12/12 | 11/12 | 12/12 |
| ollama-qwen3-8b | 11/12 | 12/12 | 12/12 | 10/12 | 11/12 | 12/12 | 11/12 |

Critical-case failures:

- **gemini-3.5-flash**: S4 TV-001: got D, expected P/N; S7 TV-007: got D, expected P/R
- **gemini-3.5-flash-lite**: S1 TV-002: got N, expected D/P
  - run error: S1 r2: InternalServerError: Error code: 503
  - run error: S1 r3: InternalServerError: Error code: 503
  - run error: S2 r1: InternalServerError: Error code: 503
  - run error: S3 r1: InternalServerError: Error code: 503
  - run error: S4 r1: InternalServerError: Error code: 503
  - run error: S5 r1: InternalServerError: Error code: 503
  - run error: S6 r1: InternalServerError: Error code: 503
  - run error: S7 r1: InternalServerError: Error code: 503
- **groq-gpt-oss-120b**: S4 TV-001: got D, expected P/N; S7 TV-007: got D, expected P/R
- **groq-qwen3.8-27b**: S4 TV-001: got D, expected P/N
- **ollama-qwen3-8b**: S1 TV-002: got N, expected D/P; S4 TV-001: got D, expected P/N; S5 TV-005: got D, expected N/P; S7 TV-007: got D, expected P/R

How to read the table:

- **Latency** is the wall-clock time of one analysis. For hosted free tiers it includes the
  provider SDK's automatic back-off after rate limiting (for example, the first
  gpt-oss-120b call took 14 s and later calls 24–109 s). It excludes the harness's own
  pauses between runs. For `qwen3:8b` it is pure CPU inference on the laptop.
- **Service errors** count calls that failed on the provider side and were not caused by
  the request:
  - Gemini 3.5 Flash-Lite returned `503 UNAVAILABLE` ("high demand") on 8 of 9 scenarios,
    plus 2 retries, for over an hour. The same request failed with and without the JSON
    schema, while one-word prompts succeeded. It was therefore scored on one run only and
    is left out of the ranking.
  - Groq qwen3.8-27b had 2 calls rejected by Groq's server-side JSON check ("Failed to
    generate JSON", S6 and S7). Both succeeded when re-run. The client now routes such a
    rejection to its normal repair retry.
- **Omitted tests:** gpt-oss-120b silently left tests out of its answer twice
  (S6: TV-010 and TV-011; plus 2 in the superseded S4 run). The post-check filled them as
  `needs_human_review` with a visible warning, as designed, and the scorer counted them as
  wrong.
- **Unneeded review flags:** `needs_human_review` or `owner_decision` on a test labelled
  clearly not affected. This column was added after the first scoring pass; it does not
  change any other number.
- **Sample size:** 84 judgments labelled by one annotator. A difference of one to three
  judgments between models is **not** meaningful. Treat the ranking as "three strong
  hosted models, one weaker local model".

### 5.1 What the models got right

All models avoided the main traps:

| Trap | Result |
|---|---|
| TV-004, brake latency 88 ms on a different clock (S1) | `not_affected` from every model. Gemini quoted the workshop note: *"brake command latency uses a different measurement clock and must not be conflated with positive torque response timing"* |
| TV-001 in the reverse case (S2, brake limit added) | `not_affected` from every model |
| TV-003, unlinked torque transient at 92 ms (S1) | Flagged by every model (`directly_affected` from Gemini, gpt-oss and qwen3:8b; `needs_human_review` from qwen3.8-27b) |
| TV-007, "80% pedal" vs "80 ms" (S1) | `needs_human_review` from every model, none treated 80% as a time |
| TV-010, 7 ms pulse vs new 5 ms filter (S3) | `directly_affected` from every model |
| TV-012, start-up timing (S1) | `not_affected` from every model |
| Approval wording | None detected in any output |

### 5.2 Disagreements, and what they say about the labels

Two critical "failures" shared by the strong models are really a **taxonomy problem**:

- **S4 TV-001 (limit relaxed to 120 ms).** Gemini, gpt-oss-120b and qwen3.8-27b all
  answered `directly_affected`. They reasoned that the 100 ms threshold in the script and
  procedure must be updated, and qwen3.8-27b added that *"the previous PASS evidence
  (94 ms) remains valid under the new limit"*. That is correct, and it matches the
  prompt's own definition (directly affected = "procedure, threshold or previous evidence
  is invalidated **or must be updated**"). The label (`possibly_affected` or
  `not_affected`) was stricter than the prompt.
- **S7 TV-007 (new thermal derating requirement).** Gemini and gpt-oss-120b answered
  `directly_affected`, because the test is the natural candidate to verify the new
  requirement once its procedure is updated. That is defensible under the same definition.

The labels were not changed after seeing the results. As a sensitivity check, if these
two cells also accepted `directly_affected`:

| Model | Lenient accuracy | Critical cases |
|---|---|---|
| gemini-3.5-flash | 99% (83/84) | 16/16 |
| groq-gpt-oss-120b | 98% (82/84) | 16/16 |
| groq-qwen3.8-27b | 98% (82/84) | 16/16 |
| ollama-qwen3-8b | 96% (81/84) | 14/16 |

**Lesson for the application.** A single status cannot distinguish "re-run the test,
the old evidence no longer holds" from "update the script or procedure text, the
evidence still holds". The application should carry that distinction as an explicit
field next to the status.

### 5.3 Genuine errors

- **qwen3:8b (local):**
  - S1 TV-002 marked `not_affected` (a missed impact). It reasoned that the test *"does
    not measure timing"*, which is exactly why the old PASS cannot show 80 ms compliance.
    It also attributed the comment "Timing not reported in old evidence" to the workshop
    notes, which is wrong.
  - S5 TV-005 marked `directly_affected` for a pure rewording, which is over-flagging.
- **Gemini 3.5 Flash-Lite:** the same S1 TV-002 miss in its only completed run.
- **gpt-oss-120b:** the omitted tests above, and the least stable S1 statuses (9/12
  identical over 3 runs).
- **Minor:** qwen3.8-27b flagged unrelated TV-003 as `possibly_affected` in S3 and S6, and
  gpt-oss-120b's two `needs_human_review` answers in S6 are the post-check fill-ins for
  its omitted tests.

## 6. Recommendation

| | Groq qwen3.8-27b | Gemini 3.5 Flash | Groq gpt-oss-120b | Local qwen3:8b |
|---|---|---|---|---|
| Accuracy (pre-registered / sensitivity) | 96% / 98% | 96% / 99% | 95% / 98% | 94% / 96% |
| Critical cases (pre-registered / sensitivity) | 15/16 / 16/16 | 14/16 / 16/16 | 14/16 / 16/16 | 12/16 / 14/16 |
| Missed impacts | 0 | 0 | 0 | 1 |
| Omitted tests | 0 | 0 | 4 | 0 |
| S1 consistency (3 runs) | **12/12** | 11/12 | 9/12 | 9/12 |
| Structured-output failures | 2 server-side rejections, recovered | 0 | 1 truncation (harness issue, fixed) | 0 |
| Median latency per analysis | **7 s** | 137 s | 46 s | 510 s (CPU) |
| Free-tier friction | Low per-minute token cap: waits of 1–4 min when runs are back to back | Slow; another model on the same tier was unavailable for over an hour | Same cap as Groq qwen | None, but 5 GB download and about 8.5 min per run |
| Cost | Free | Free | Free | Free |
| Reviewer needs | Free Groq key | Free Google key | Free Groq key | Ollama + 5 GB |

**Recommended configuration:**

1. **Primary: Groq `qwen/qwen3.8-27b`.** It has the best critical-case score and perfect
   consistency, made no missed impacts and omitted nothing, and takes about 7 s per
   analysis. That makes live re-analysis after an edit practical in a demo. Its two
   server-side JSON rejections are recovered by the client's repair retry.
2. **Fallback: Gemini `gemini-3.5-flash`.** It has the most dependable structured output
   in this run (9/9 first try, no omissions, no service errors) and the best strict
   accuracy, but takes 1–6 min per analysis on the free tier. Switching is configuration
   only (`LLM_PROVIDER=gemini`, `LLM_MODEL=gemini-3.5-flash`).
3. **Offline option: Ollama `qwen3:8b`.** Supported and documented. It is usable, and it
   avoided every named trap, but it is clearly weaker (1 missed impact, over-flagging a
   cosmetic change) and slow on this laptop (8–13 min per analysis). It is not the
   default.
4. **Reviewers without credentials: replay.** The application ships the recorded outputs
   of the primary model for the provided inputs, labelled as replayed, with model and
   date.

Not recommended: gpt-oss-120b, which silently omitted tests; Gemini 3.5 Flash-Lite, which
was unavailable for most of the run; GitHub Models, which is retired.

### Limitations of this evaluation

- One annotator, 84 judgments, one register. The ranking among the three strong models
  is within noise.
- Free-tier behaviour (latency, rate limits, availability) was observed on one afternoon
  and can change without notice. Model IDs may be retired, as GitHub Models and
  `gemini-2.5-flash` were.
- The quality of the reasons was checked by hand on the disputed cases only (quoted
  above), not scored systematically.
- Temperature 0 does not make hosted models deterministic. The consistency column
  measures exactly that.

### Reproducing

```bash
uv sync
cp .env.example .env            # add GEMINI_API_KEY and/or GROQ_API_KEY
uv run python eval/smoke.py groq:qwen/qwen3.8-27b gemini:gemini-3.5-flash   # one tiny call each
uv run python eval/evaluate.py build    # regenerate scenario .docx (already committed)
uv run python eval/evaluate.py score --version v1     # recompute the v1 tables above from the stored runs
uv run python eval/evaluate.py score --version v3     # same for the later prompt versions (section 7)
uv run python eval/evaluate.py score --version v1 --labels v2   # v1 outputs with the two relabelled cells
# new runs use the CURRENT prompt (v3) and write to eval/results/v3/
uv run python eval/evaluate.py run --only groq-qwen3.8-27b
# local model: ollama pull qwen3:8b && LLM_TIMEOUT_S=1800 uv run python eval/evaluate.py run --only ollama-qwen3-8b
```

The v1 and v2 prompts are frozen in [`eval/prompts/`](../eval/prompts/) with their output
schemas. The harness always runs the current prompt, so the v1 runs are reproduced by
re-scoring the stored outputs, not by re-running them.

## 7. Adding `required_actions` (prompts v2 and v3)

### Why

A single status mixed two questions: how strongly a test is tied to the change, and what
the engineer has to do. In S4 (limit relaxed to 120 ms) three strong models called TV-001
`directly_affected` because its script must change, while its old 94 ms evidence still
holds. The answer was reasonable and my label was not. Each result now carries a list
`required_actions`: `rerun`, `update_procedure`, `fix_link`, `owner_decision` or `none`.

- `fix_link` is **set by the code** from the parsed link status (missing, TBD, unknown or
  removed requirement). If the model returns it for a test with a valid link it is removed
  with a warning. The model is told not to output it.
- The model decides the rest. Whether old evidence still meets the new requirement
  needs judgment, so `rerun` and `update_procedure` come from the LLM.
- Consequence for the UI and report: `fix_link` comes from the register data, not from
  the model's text. A test can read "No action required" in the model's recommendation and
  still carry `fix_link` (TV-012 in S1). The UI must label the source.

### What changed between versions

| Version | Change |
|---|---|
| v1 | Status only. Frozen in `eval/prompts/v1/`. |
| v2 | Adds `required_actions`. Status definitions reworded: status means relevance, the action means work. |
| v3 | Written after reading v2's results: `needs_human_review` no longer applies to a broken link alone (the code flags those), and a rewording is stated to affect no test directly. |

### Results (Groq `qwen/qwen3.8-27b` only)

Same 84 judgments. Only this model was re-run; other models were not tested with v2 or v3,
so nothing here changes the model comparison in section 5.

| | v1, original labels | v1, relabelled cells* | v2 | v3 |
|---|---|---|---|---|
| Valid on first try | 9/9 | 9/9 | 8/9 | 9/9 |
| Lenient accuracy | 96% (81/84) | 98% (82/84) | 99% (83/84) | 99% (83/84) |
| Critical cases | 15/16 | 16/16 | 15/16 | 15/16 |
| Missed impacts | 0 | 0 | 0 | 0 |
| Unneeded review flags | 5 | 5 | **10** | 5 |
| Required-action accuracy | n/a | n/a | 15/16 | 15/16 |
| Same status on 3 S1 runs | 12/12 | 12/12 | 12/12 | 12/12 |
| Strict accuracy (preferred label) | 82% | 82% | 75% | 76% |

\* `--labels v2`: the two cells (S4 TV-001, S7 TV-007) where a `directly_affected`
answer is also accepted, see section 5.2. The relabelled column is the like-for-like
baseline for v2 and v3, which are always scored with those cells.

Reading it honestly:

- **Prompt v2/v3 did not improve status accuracy.** Against the like-for-like baseline,
  v3 gets 83/84 and v1 gets 82/84: noise. The "99%" is mostly the relabelling.
- **One critical case got worse.** S5 TV-005, where DGN-04 is only reworded, was
  `not_affected` in v1 and is `directly_affected` in v2 and v3. The model's own reason says
  "the behavior is unchanged", so its output contradicts itself. The v3 wording meant to
  prevent this and did not.
- **v2 increased review noise** (10 unneeded flags, up from 5) because it told the model
  to use `needs_human_review` for broken links. v3 undid that.
- **Strict accuracy fell (82% to 76%)** largely because the code now flags broken links.
  The model therefore says `not_affected` plus `fix_link` for the orphaned TV-008 where
  v1 said `needs_human_review`, and my "preferred" labels expected the latter. This is a
  mismatch between design and labels, not worse judgment. Labels were not changed.
- **The new field works.** 15/16 labelled cases are right. The miss is S1 TV-002 (linked
  to DR-01, no timing in its old evidence): the model asked for `owner_decision` where
  `rerun` was labelled.
- **First S7 call in v2** fell back to JSON mode after Groq rejected its first attempt
  (`does not match the expected schema`). The client now routes this rejection to its
  normal repair retry, and v3 had no such fallback.

### A consistency check in the application

The S5 TV-005 failure is cheap to detect: the model interpreted the change to DGN-04 as
`reworded_same_meaning` and then marked a test related only to DGN-04 as
`directly_affected`. The post-check now adds a warning for exactly this contradiction.
It does **not** change the status, because silently overriding the model would hide a
disagreement an engineer should see. Applied to the stored outputs it fires for v2 and v3
and stays silent for v1, where the status was correct. It makes the problem visible; it
does not fix the model's answer, and the S5 TV-005 score is unchanged.

### Decision

Prompt **v3** with Groq `qwen/qwen3.8-27b` is the configuration used by the application,
decided by the project owner after reviewing the labels. The open S5 TV-005 failure and
the other limitations are tracked in [known_issues.md](known_issues.md).

### Caveats

- **v3 is not an independent test.** Its wording was written after reading v2's failures
  on these same seven scenarios, so some fit to this dataset is likely. A different
  register or change could behave differently.
- One model, one run per scenario (S1 three times), 84 judgments, one annotator.
- The action labels (`must` and `must_not` lists in [`eval/dataset.yaml`](../eval/dataset.yaml))
  cover 16 judgments and were written before the v2 run. `fix_link` is not scored because
  the code sets it.
