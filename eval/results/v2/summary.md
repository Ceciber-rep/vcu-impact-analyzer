| Model | Runs ok | Valid 1st try | Lenient acc. | Strict acc. | Critical cases | Missed impacts | Over-flags (D) | Unneeded review flags | Omitted tests | Approval wording | S1 consistency | Median latency | Median output tokens | Service errors |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| groq-qwen3.8-27b | 9/9 | 89% (8/9) | 99% (83/84) | 75% (63/84) | 94% (15/16) | 0 | 1 | 10 | 0 | 0 | 12/12 over 3 runs | 5 s | 1775 | 0 |

Per-scenario lenient score (first repetition):

| Model | S1 | S2 | S3 | S4 | S5 | S6 | S7 |
|---|---|---|---|---|---|---|---|
| groq-qwen3.8-27b | 12/12 | 12/12 | 12/12 | 12/12 | 11/12 | 12/12 | 12/12 |

Required actions (labelled cases, first repetition):

- **groq-qwen3.8-27b**: 94% (15/16); failures: S7 TV-007: got ['fix_link', 'owner_decision'], rule {'must': ['update_procedure']}

Critical-case failures:

- **groq-qwen3.8-27b**: S5 TV-005: got D, expected N/P
