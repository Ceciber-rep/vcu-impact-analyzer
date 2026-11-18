# After the application's post-check (same stored outputs, rewording safety net applied)

Prompt version v1, labels v2.

## Original scenarios (S1 to S7)

| Model | Runs ok | Valid 1st try | Lenient acc. | Strict acc. | Critical cases | Missed impacts | Over-flags (D) | Unneeded review flags | Omitted tests | Approval wording | S1 consistency | Median latency | Median output tokens | Service errors | Post-check adjustments |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| gemini-3.5-flash | 9/9 | 100% (9/9) | 99% (83/84) | 85% (71/84) | 100% (16/16) | 0 | 1 | 6 | 0 | 0 | 11/12 over 3 runs | 137 s | 2023 | 0 | 0 |
| gemini-3.5-flash-lite | 1/9 | 100% (1/1) | 92% (11/12) | 75% (9/12) | 83% (5/6) | 1 | 0 | 0 | 0 | 0 | n/a | 7 s | 1721 | 10 | 0 |
| groq-gpt-oss-120b | 9/9 | 100% (9/9) | 98% (82/84) | 81% (68/84) | 100% (16/16) | 0 | 0 | 6 | 4 | 0 | 9/12 over 3 runs | 46 s | 2697 | 0 | 0 |
| groq-qwen3.8-27b | 9/9 | 100% (9/9) | 98% (82/84) | 82% (69/84) | 100% (16/16) | 0 | 0 | 5 | 0 | 0 | 12/12 over 3 runs | 7 s | 1699 | 2 | 0 |
| ollama-qwen3-8b | 9/9 | 100% (9/9) | 98% (82/84) | 87% (73/84) | 94% (15/16) | 1 | 1 | 3 | 0 | 0 | 9/12 over 3 runs | 510 s | 3067 | 0 | 1 |

Per-scenario lenient score (first repetition):

| Model | S1 | S2 | S3 | S4 | S5 | S6 | S7 |
|---|---|---|---|---|---|---|---|
| gemini-3.5-flash | 12/12 | 12/12 | 12/12 | 11/12 | 12/12 | 12/12 | 12/12 |
| gemini-3.5-flash-lite | 11/12 | failed | failed | failed | failed | failed | failed |
| groq-gpt-oss-120b | 12/12 | 12/12 | 12/12 | 12/12 | 12/12 | 10/12 | 12/12 |
| groq-qwen3.8-27b | 12/12 | 12/12 | 11/12 | 12/12 | 12/12 | 11/12 | 12/12 |
| ollama-qwen3-8b | 11/12 | 12/12 | 12/12 | 11/12 | 12/12 | 12/12 | 12/12 |

Required actions (labelled cases, first repetition):

- **gemini-3.5-flash**: 44% (7/16); failures: S1 TV-001: got ['none'], rule {'must': ['rerun', 'update_procedure']}; S1 TV-002: got ['none'], rule {'must': ['rerun']}; S1 TV-003: got ['fix_link'], rule {'must': ['rerun']}; S2 TV-002: got ['none'], rule {'must': ['rerun']}; S2 TV-004: got ['none'], rule {'must': ['rerun', 'update_procedure']}; S2 TV-011: got ['none'], rule {'must': ['rerun']}; S3 TV-010: got ['none'], rule {'must': ['update_procedure']}; S4 TV-001: got ['none'], rule {'must': ['update_procedure'], 'must_not': ['rerun']}; S7 TV-007: got ['fix_link'], rule {'must': ['update_procedure']}
- **gemini-3.5-flash-lite**: 40% (2/5); failures: S1 TV-001: got ['none'], rule {'must': ['rerun', 'update_procedure']}; S1 TV-002: got ['none'], rule {'must': ['rerun']}; S1 TV-003: got ['fix_link'], rule {'must': ['rerun']}
- **groq-gpt-oss-120b**: 44% (7/16); failures: S1 TV-001: got ['none'], rule {'must': ['rerun', 'update_procedure']}; S1 TV-002: got ['none'], rule {'must': ['rerun']}; S1 TV-003: got ['fix_link'], rule {'must': ['rerun']}; S2 TV-002: got ['none'], rule {'must': ['rerun']}; S2 TV-004: got ['none'], rule {'must': ['rerun', 'update_procedure']}; S2 TV-011: got ['none'], rule {'must': ['rerun']}; S3 TV-010: got ['none'], rule {'must': ['update_procedure']}; S4 TV-001: got ['none'], rule {'must': ['update_procedure'], 'must_not': ['rerun']}; S7 TV-007: got ['fix_link'], rule {'must': ['update_procedure']}
- **groq-qwen3.8-27b**: 44% (7/16); failures: S1 TV-001: got ['none'], rule {'must': ['rerun', 'update_procedure']}; S1 TV-002: got ['none'], rule {'must': ['rerun']}; S1 TV-003: got ['fix_link'], rule {'must': ['rerun']}; S2 TV-002: got ['none'], rule {'must': ['rerun']}; S2 TV-004: got ['none'], rule {'must': ['rerun', 'update_procedure']}; S2 TV-011: got ['none'], rule {'must': ['rerun']}; S3 TV-010: got ['none'], rule {'must': ['update_procedure']}; S4 TV-001: got ['none'], rule {'must': ['update_procedure'], 'must_not': ['rerun']}; S7 TV-007: got ['fix_link'], rule {'must': ['update_procedure']}
- **ollama-qwen3-8b**: 44% (7/16); failures: S1 TV-001: got ['none'], rule {'must': ['rerun', 'update_procedure']}; S1 TV-002: got ['none'], rule {'must': ['rerun']}; S1 TV-003: got ['fix_link'], rule {'must': ['rerun']}; S2 TV-002: got ['none'], rule {'must': ['rerun']}; S2 TV-004: got ['none'], rule {'must': ['rerun', 'update_procedure']}; S2 TV-011: got ['none'], rule {'must': ['rerun']}; S3 TV-010: got ['none'], rule {'must': ['update_procedure']}; S4 TV-001: got ['none'], rule {'must': ['update_procedure'], 'must_not': ['rerun']}; S7 TV-007: got ['fix_link'], rule {'must': ['update_procedure']}

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

- **gemini-3.5-flash**: none
- **gemini-3.5-flash-lite**: S1 TV-002: got N, expected D/P
  - run error: S1 r2: InternalServerError: Error code: 503
  - run error: S1 r3: InternalServerError: Error code: 503
  - run error: S2 r1: InternalServerError: Error code: 503
  - run error: S3 r1: InternalServerError: Error code: 503
  - run error: S4 r1: InternalServerError: Error code: 503
  - run error: S5 r1: InternalServerError: Error code: 503
  - run error: S6 r1: InternalServerError: Error code: 503
  - run error: S7 r1: InternalServerError: Error code: 503
- **groq-gpt-oss-120b**: none
- **groq-qwen3.8-27b**: none
- **ollama-qwen3-8b**: S1 TV-002: got N, expected D/P
