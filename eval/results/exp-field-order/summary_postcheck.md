# After the application's post-check (same stored outputs, rewording safety net applied)

Prompt version exp-field-order, labels exp-field-order.

## Original scenarios (S1 to S7)

| Model | Runs ok | Valid 1st try | Lenient acc. | Strict acc. | Critical cases | Missed impacts | Over-flags (D) | Unneeded review flags | Omitted tests | Approval wording | S1 consistency | Median latency | Median output tokens | Service errors | Post-check adjustments |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| groq-qwen3.8-27b | 9/9 | 89% (8/9) | 99% (83/84) | 75% (63/84) | 100% (16/16) | 0 | 0 | 5 | 0 | 0 | 11/12 over 3 runs | 12 s | 1962 | 0 | 1 |

Per-scenario lenient score (first repetition):

| Model | S1 | S2 | S3 | S4 | S5 | S6 | S7 |
|---|---|---|---|---|---|---|---|
| groq-qwen3.8-27b | 12/12 | 12/12 | 12/12 | 12/12 | 12/12 | 11/12 | 12/12 |

Required actions (labelled cases, first repetition):

- **groq-qwen3.8-27b**: 75% (12/16); failures: S1 TV-001: got ['rerun'], rule {'must': ['rerun', 'update_procedure']}; S4 TV-001: got ['rerun', 'update_procedure'], rule {'must': ['update_procedure'], 'must_not': ['rerun']}; S4 TV-003: got ['fix_link', 'owner_decision', 'rerun', 'update_procedure'], rule {'must_not': ['rerun']}; S5 TV-005: got ['update_procedure'], rule {'must_not': ['rerun', 'update_procedure']}

Statuses changed by the post-check:

- **groq-qwen3.8-27b**: S5 TV-005

Missed impacts (not_affected where the label does not allow it):

- **groq-qwen3.8-27b**: none

Critical-case failures:

- **groq-qwen3.8-27b**: none
