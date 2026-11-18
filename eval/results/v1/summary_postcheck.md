# After the application's post-check (same stored outputs, rewording safety net applied)

Prompt version v1, labels v1.

## Original scenarios (S1 to S7)

| Model | Runs ok | Valid 1st try | Lenient acc. | Strict acc. | Critical cases | Missed impacts | Over-flags (D) | Unneeded review flags | Omitted tests | Approval wording | S1 consistency | Median latency | Median output tokens | Service errors | Post-check adjustments |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| gemini-3.5-flash | 9/9 | 100% (9/9) | 96% (81/84) | 85% (71/84) | 88% (14/16) | 0 | 3 | 6 | 0 | 0 | 11/12 over 3 runs | 137 s | 2023 | 0 | 0 |
| gemini-3.5-flash-lite | 1/9 | 100% (1/1) | 92% (11/12) | 75% (9/12) | 83% (5/6) | 1 | 0 | 0 | 0 | 0 | n/a | 7 s | 1721 | 10 | 0 |
| groq-gpt-oss-120b | 9/9 | 100% (9/9) | 95% (80/84) | 81% (68/84) | 88% (14/16) | 0 | 2 | 6 | 4 | 0 | 9/12 over 3 runs | 46 s | 2697 | 0 | 0 |
| groq-qwen3.8-27b | 9/9 | 100% (9/9) | 96% (81/84) | 82% (69/84) | 94% (15/16) | 0 | 1 | 5 | 0 | 0 | 12/12 over 3 runs | 7 s | 1699 | 2 | 0 |
| ollama-qwen3-8b | 9/9 | 100% (9/9) | 95% (80/84) | 87% (73/84) | 81% (13/16) | 1 | 3 | 3 | 0 | 0 | 9/12 over 3 runs | 510 s | 3067 | 0 | 1 |

Per-scenario lenient score (first repetition):

| Model | S1 | S2 | S3 | S4 | S5 | S6 | S7 |
|---|---|---|---|---|---|---|---|
| gemini-3.5-flash | 12/12 | 12/12 | 12/12 | 10/12 | 12/12 | 12/12 | 11/12 |
| gemini-3.5-flash-lite | 11/12 | failed | failed | failed | failed | failed | failed |
| groq-gpt-oss-120b | 12/12 | 12/12 | 12/12 | 11/12 | 12/12 | 10/12 | 11/12 |
| groq-qwen3.8-27b | 12/12 | 12/12 | 11/12 | 11/12 | 12/12 | 11/12 | 12/12 |
| ollama-qwen3-8b | 11/12 | 12/12 | 12/12 | 10/12 | 12/12 | 12/12 | 11/12 |

Statuses changed by the post-check:

- **gemini-3.5-flash**: none
- **gemini-3.5-flash-lite**: none
- **groq-gpt-oss-120b**: none
- **groq-qwen3.8-27b**: none
- **ollama-qwen3-8b**: S5 TV-005

Missed impacts (not_affected where the label does not allow it):

- **gemini-3.5-flash**: none
- **gemini-3.5-flash-lite**: S1 TV-002
- **groq-gpt-oss-120b**: none
- **groq-qwen3.8-27b**: none
- **ollama-qwen3-8b**: S1 TV-002

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
- **ollama-qwen3-8b**: S1 TV-002: got N, expected D/P; S4 TV-001: got D, expected P/N; S7 TV-007: got D, expected P/R
