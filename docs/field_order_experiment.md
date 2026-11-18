# Experiment: does the order of the output fields explain the S5 contradiction?

Branch `exp/field-order`. **Not merged**, and the result below says there is no reason to merge it.

## Question

With prompt v3, Groq `qwen/qwen3.8-27b` marks S5 TV-005 `directly_affected` although its own
`change_interpretations` reads the change as `reworded_same_meaning`. The stored raw outputs show that qwen
writes its JSON keys in alphabetical order (29 of 30 runs), so `assessments` is generated **before**
`change_interpretations`: the model cannot condition its statuses on its own reading of the change. If that were the
cause, generating the interpretation first should remove the contradiction.

## Method

- One change, to the output schema only: the JSON name of the top-level field `assessments` becomes
  `test_assessments`, which sorts after `change_interpretations` (a pydantic alias in `models.py`; the Python name,
  the code and the stored results are unchanged). The new schema differs from the frozen one by that key name only
  (checked programmatically). `SYSTEM_PROMPT` and `build_user_prompt` are untouched (the prompt never names the field).
- Groq qwen3.8-27b, temperature 0, the same 7 original scenarios (S1 three times) and register. S5 was repeated
  four more times (5 runs in all). The held-out scenarios were not used, so they are not tuned on.
- Results are in `eval/results/exp-field-order/`. The model's own statuses are scored (the raw view, which undoes the
  application's recorded corrections), next to the unchanged v3 baseline.

## Results

| | v3 baseline (`assessments`) | Renamed field (`test_assessments`) |
|---|---|---|
| First key in the model's output | `assessments` (alphabetical) | `change_interpretations` in all 13 runs |
| S5 TV-005, the model's own status | `directly_affected` | `directly_affected` in **5 of 5** runs |
| Model's reading of the S5 change | `reworded_same_meaning` | `reworded_same_meaning` in 5 of 5 |
| Critical cases (raw, 84 cells) | 15/16 | 15/16 (the same cell, S5 TV-005) |
| Lenient accuracy (raw) | 83/84 | 82/84 |
| After the application's post-check | 84/84, 16/16 | 83/84, 16/16 |
| S1 outputs over three runs | byte-identical, 12/12 | not identical (1962, 1966, 2069 tokens), 11/12 |
| Repair retries | 0 | 1 (Groq rejected the generated JSON once in S1) |

The model's own status differs from the baseline on 6 of 84 cells: S1 TV-002 and TV-003
(possibly to directly affected), S4 TV-003 and S6 TV-006 (possibly affected to needs human review), S7 TV-007
(directly affected to needs human review) and S7 TV-008 (needs human review to not affected). None of them is
systematically better or worse; the lenient score moves by one cell.

## Conclusion

- **The hypothesis is not supported.** With the interpretation generated first, qwen reads the change as a pure rewording
  and still marks the test directly affected, five times out of five. Field order is not what causes the S5
  contradiction, so the safety net in the application is still needed, and reordering is not a fix.
- The cause is therefore unexplained. A candidate that this experiment does **not** test: the status definition in the
  prompt ("the test verifies behaviour that the change alters") can be read as "the test is linked to the requirement that
  changed", which S5 TV-005 is. Changing the prompt is out of scope here (it is frozen), and it would be tuned on the
  scenario that motivated it.
- A schema change is not free: the same prompt with a different key name changed 6 cells, made the model's
  S1 outputs vary where they had been byte-identical, and added one provider-side JSON rejection. That is itself a reminder
  that the "12/12 consistency" of the baseline was a property of that exact input, not of the model's reasoning.

## Limits

One model, one provider, 9 runs plus 4 repeats, scenarios S1 to S7 only, no held-out check. Groq's constrained decoding
(not the model alone) may be what orders the keys, and the experiment does not separate the two. A single schema change is
not a controlled ablation.
