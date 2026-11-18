# After the application's post-check (same stored outputs, rewording safety net applied)

Prompt version v3, labels v3.

## Original scenarios (S1 to S7)

| Model | Runs ok | Valid 1st try | Lenient acc. | Strict acc. | Critical cases | Missed impacts | Over-flags (D) | Unneeded review flags | Omitted tests | Approval wording | S1 consistency | Median latency | Median output tokens | Service errors | Post-check adjustments |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| gemini-3.5-flash | 9/9 | 100% (9/9) | 98% (82/84) | 80% (67/84) | 100% (16/16) | 0 | 2 | 0 | 0 | 0 | 10/12 over 3 runs | 97 s | 1958 | 0 | 0 |
| groq-gpt-oss-120b | 9/9 | 100% (9/9) | 99% (83/84) | 81% (68/84) | 94% (15/16) | 1 | 0 | 3 | 0 | 0 | 11/12 over 3 runs | 9 s | 3092 | 2 | 0 |
| groq-qwen3.8-27b | 9/9 | 100% (9/9) | 100% (84/84) | 77% (65/84) | 100% (16/16) | 0 | 0 | 5 | 0 | 0 | 12/12 over 3 runs | 6 s | 1781 | 0 | 1 |

Per-scenario lenient score (first repetition):

| Model | S1 | S2 | S3 | S4 | S5 | S6 | S7 |
|---|---|---|---|---|---|---|---|
| gemini-3.5-flash | 12/12 | 12/12 | 12/12 | 11/12 | 12/12 | 11/12 | 12/12 |
| groq-gpt-oss-120b | 11/12 | 12/12 | 12/12 | 12/12 | 12/12 | 12/12 | 12/12 |
| groq-qwen3.8-27b | 12/12 | 12/12 | 12/12 | 12/12 | 12/12 | 12/12 | 12/12 |

Required actions (labelled cases, first repetition):

- **gemini-3.5-flash**: 100% (16/16); failures: none
- **groq-gpt-oss-120b**: 94% (15/16); failures: S1 TV-003: got ['fix_link', 'owner_decision'], rule {'must': ['rerun']}
- **groq-qwen3.8-27b**: 94% (15/16); failures: S1 TV-002: got ['owner_decision'], rule {'must': ['rerun']}

Statuses changed by the post-check:

- **gemini-3.5-flash**: none
- **groq-gpt-oss-120b**: none
- **groq-qwen3.8-27b**: S5 TV-005

Missed impacts (not_affected where the label does not allow it):

- **gemini-3.5-flash**: none
- **groq-gpt-oss-120b**: S1 TV-007
- **groq-qwen3.8-27b**: none

Critical-case failures:

- **gemini-3.5-flash**: none
- **groq-gpt-oss-120b**: S1 TV-007: got N, expected P/R
- **groq-qwen3.8-27b**: none

## Held-out scenarios (37 cells, scored separately)

| Model | Runs ok | Valid 1st try | Lenient acc. | Strict acc. | Critical cases | Missed impacts | Over-flags (D) | Unneeded review flags | Omitted tests | Approval wording | S1 consistency | Median latency | Median output tokens | Service errors | Post-check adjustments |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| gemini-3.5-flash | 3/3 | 100% (3/3) | 97% (36/37) | 81% (30/37) | 94% (15/16) | 0 | 1 | 0 | 0 | 0 | n/a | 94 s | 2212 | 0 | 0 |
| groq-gpt-oss-120b | 3/3 | 100% (3/3) | 89% (33/37) | 68% (25/37) | 81% (13/16) | 2 | 2 | 1 | 0 | 0 | n/a | 24 s | 3944 | 2 | 0 |
| groq-qwen3.8-27b | 3/3 | 100% (3/3) | 97% (36/37) | 73% (27/37) | 94% (15/16) | 0 | 1 | 2 | 0 | 0 | n/a | 7 s | 1940 | 0 | 0 |

Per-scenario lenient score (first repetition):

| Model | S8 | S9 | S10 |
|---|---|---|---|
| gemini-3.5-flash | 11/12 | 12/12 | 13/13 |
| groq-gpt-oss-120b | 10/12 | 12/12 | 11/13 |
| groq-qwen3.8-27b | 11/12 | 12/12 | 13/13 |

Required actions (labelled cases, first repetition):

- **gemini-3.5-flash**: 100% (7/7); failures: none
- **groq-gpt-oss-120b**: 57% (4/7); failures: S8 TV-001: got ['none'], rule {'must': ['update_procedure']}; S9 TV-002: got ['owner_decision'], rule {'must': ['rerun']}; S10 TV-013: got ['rerun', 'update_procedure'], rule {'must_not': ['rerun', 'update_procedure']}
- **groq-qwen3.8-27b**: 100% (7/7); failures: none

Related requirements (labelled cases, first repetition):

- **gemini-3.5-flash**: 86% (6/7); failures: S9 TV-011: got ['VCU-BRK-03', 'VCU-DR-01'], rule {'must': ['VCU-BRK-03'], 'must_not': ['VCU-DR-01']}
- **groq-gpt-oss-120b**: 86% (6/7); failures: S8 TV-001: got [], rule {'must': ['VCU-DR-01']}
- **groq-qwen3.8-27b**: 86% (6/7); failures: S9 TV-002: got ['VCU-BRK-03'], rule {'must': ['VCU-DR-01', 'VCU-BRK-03']}

Statuses changed by the post-check:

- **gemini-3.5-flash**: none
- **groq-gpt-oss-120b**: none
- **groq-qwen3.8-27b**: none

Missed impacts (not_affected where the label does not allow it):

- **gemini-3.5-flash**: none
- **groq-gpt-oss-120b**: S8 TV-001, S10 TV-007
- **groq-qwen3.8-27b**: none

Critical-case failures:

- **gemini-3.5-flash**: S8 TV-002: got D, expected N/P
- **groq-gpt-oss-120b**: S8 TV-001: got N, expected D/P; S10 TV-007: got N, expected P/R; S10 TV-013: got D, expected N/P
- **groq-qwen3.8-27b**: S8 TV-002: got D, expected N/P
