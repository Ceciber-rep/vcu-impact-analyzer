# Engineering impact summary

VCU-42 | Driver demand and safety controls · generated 2026-11-17 17:40 UTC

> **Recommendations only.** This report gives recommendations for engineering review. The test register is treated as evidence from earlier campaigns, not as approval. Nothing in this report approves a requirement, a test or a result: final approval belongs to the authorized owner.

**Source of the assessment:** Replayed: real output of groq:qwen/qwen3.8-27b recorded at 2026-11-16T17:42:44+00:00 (evaluation scenario S1: DR-01 response time tightened 100 -> 80 ms (real revision B)). No model was called now. Prompt version v3.

## Inputs

| Role | File | Revision / content | SHA-256 (first 12) |
|---|---|---|---|
| Baseline specification | VCU_Spec_Baseline.docx | Revision A \| baseline | `98d375702420` |
| Revised specification | VCU_Spec_Revised.docx | Revision B \| candidate change | `e65386c79cd3` |
| Test register | VCU_Test_Register.xlsx | 12 tests | `2d18e397ffe2` |

## 1. What changed

### VCU-DR-01 · Driver torque response (modified)

When accelerator pedal demand rises above 70% while drive is enabled, the torque controller shall issue the demanded positive torque within ~~100~~**80** milliseconds, measured from validated pedal input to the first commanded torque response.

Numeric changes: 100 milliseconds → 80 milliseconds

**LLM interpretation:** tightened: The customer has requested a tighter response-time objective for the driver torque response, reducing the maximum allowed time from 100 ms to 80 ms. This requires updating test procedures and scripts that use the 100 ms threshold and rerunning tests to generate new evidence that meets the stricter limit.

Other document changes (not requirements):

- **Front matter:** VCU-42 | Driver demand and safety controls Engineering specification · Revision ~~A~~**B** | ~~baseline~~**candidate change** · Supplier demonstration only
- **Document record:** Record | Value System | VCU-42 (fictional simulation) Document owner | Vehicle Controls Engineering Document state | Revision ~~A~~**B** | ~~baseline~~**candidate change** Note | This document is intended for engineering review, not production use.
- **4 Revision notes:** before: ~~Initial validation baseline for this exercise package. The team has completed an earlier bench campaign against this revision.~~; after: **The customer has requested a tighter response-time objective for the driver torque response. The document has been updated for engineering assessment; test procedures and evidence have not yet been reapproved.**

Unchanged requirements: VCU-DR-02, VCU-BRK-03, VCU-DGN-04, VCU-LOG-05, VCU-MOD-06

## 2. Impact summary

| Directly affected | Possibly affected | Needs human review | Not affected | 
|---|---|---|---|
| 1 | 2 | 1 | 8 | 

### Work list

| Required action | Tests |
|---|---|
| Re-run test | TV-001 Pedal step response; TV-003 High load torque transient |
| Update procedure | TV-001 Pedal step response; TV-003 High load torque transient |
| Fix requirement link | TV-003 High load torque transient; TV-007 Acceleration at thermal load; TV-008 Legacy diagnostic replay; TV-012 Wake-up timing |
| Owner decision | TV-002 Brake / pedal arbitration; TV-003 High load torque transient; TV-007 Acceleration at thermal load |

"Fix requirement link" is derived by the application from the register (missing, TBD, unknown or removed requirement links), not by the model.

## 3. Assessment per test

All tests in the register are listed, including those judged not affected. \* = action set from the register links.

| Test | Name | Status | Confidence | Required actions | Why |
|---|---|---|---|---|---|
| TV-001 | Pedal step response | Directly affected | high | Re-run test, Update procedure | The test directly verifies the driver torque response time limit, which was tightened from 100 ms to 80 ms. The previous result of 94 ms no longer meets the new 80 ms requirement, and the test script still uses the old 100 ms threshold. |
| TV-002 | Brake / pedal arbitration | Possibly affected | medium | Owner decision | The test is linked to the changed requirement VCU-DR-01 and involves high pedal demand, but the previous evidence does not report timing data. It is unclear if the test procedure includes a timing assertion for torque response, making it impossible to determine if the old evidence is valid for the new 80 ms limit. |
| TV-003 | High load torque transient | Possibly affected | medium | Re-run test, Update procedure, Fix requirement link *, Owner decision | The test measures torque response time (92 ms) under high load, which is directly related to the VCU-DR-01 change. The previous result of 92 ms exceeds the new 80 ms limit, and the legacy script uses a 95 ms tolerance. The missing link prevents definitive confirmation, but the content strongly suggests relevance. |
| TV-007 | Acceleration at thermal load | Needs human review | low | Fix requirement link *, Owner decision | The test involves torque delivery at high pedal demand, which may relate to VCU-DR-01, but the requirement link is TBD and ownership is unclear. The available information is insufficient to determine if the test is affected by the change. |
| TV-004 | Brake actuator response | Not affected | high | None | The test verifies brake command latency, which is measured by a different clock than the positive torque response time in VCU-DR-01. The change to VCU-DR-01 does not affect the brake override requirement or its measurement method. |
| TV-005 | Sensor failure: wheel speed | Not affected | high | None | The test verifies sensor degradation behavior, which is unrelated to the driver torque response time change in VCU-DR-01. |
| TV-006 | Mode event audit trail | Not affected | high | None | The test verifies trace and evidence logging for mode changes, which is unrelated to the driver torque response time change in VCU-DR-01. |
| TV-008 | Legacy diagnostic replay | Not affected | high | Fix requirement link * | The test is linked to an unknown requirement and involves diagnostic replay, which is unrelated to the driver torque response time change in VCU-DR-01. The broken link alone is not a reason for needs_human_review, and the content is clearly unrelated. |
| TV-009 | Sport profile torque ramp | Not affected | medium | None | The test verifies torque ramp profiles under different modes, which is related to VCU-MOD-06, not VCU-DR-01. The comment explicitly states there is no quantitative response-time assertion, so the change to the 80 ms limit in VCU-DR-01 does not directly affect this test. |
| TV-010 | Pedal signal spike | Not affected | high | None | The test verifies pedal signal filtering for transient spikes, which is unrelated to the driver torque response time change in VCU-DR-01. |
| TV-011 | Torque cancellation on braking | Not affected | high | None | The test verifies brake priority over positive torque, which is unrelated to the driver torque response time change in VCU-DR-01. |
| TV-012 | Wake-up timing | Not affected | high | Fix requirement link * | The test verifies ECU wake-up timing, which is unrelated to the driver torque response time change in VCU-DR-01. The missing link does not change the fact that the test content is clearly unrelated. |

### Details

**TV-001 · Pedal step response**: Directly affected (confidence high)
- Recommended next step: Update the test script threshold to 80 ms and rerun the test to generate new evidence.
- Evidence: Procedure explicitly checks torque response within 100 ms
- Evidence: Previous result recorded 94 ms
- Evidence: Comment notes 100 ms threshold in script
- Requirement link: VCU-DR-01 (valid) · Previous result: PASS (94 ms)

**TV-002 · Brake / pedal arbitration**: Possibly affected (confidence medium)
- Recommended next step: Review the test procedure to determine if torque response timing is measured; if so, update the limit to 80 ms and rerun.
- Evidence: Linked to VCU-DR-01
- Evidence: Comment states 'Timing not reported in old evidence'
- Evidence: Procedure involves 85% pedal demand
- Requirement link: VCU-DR-01 (valid); VCU-BRK-03 (valid) · Previous result: PASS

**TV-003 · High load torque transient**: Possibly affected (confidence medium)
- Recommended next step: Clarify the requirement link, update the tolerance to 80 ms, and rerun the test.
- Evidence: Procedure sweeps demand 75-95% and records 92 ms
- Evidence: Comment notes 'Legacy suite still checks 95 ms tolerance'
- Evidence: Missing requirement link
- Requirement link: (empty) (missing) · Previous result: PASS (92 ms)

**TV-007 · Acceleration at thermal load**: Needs human review (confidence low)
- Recommended next step: Clarify the requirement link and ownership with the system engineer.
- Evidence: Requirement link is TBD
- Evidence: Comment notes 'Ownership and source link to be clarified'
- Evidence: Procedure involves 80% pedal and torque delivery
- Requirement link: TBD (tbd) · Previous result: NOT RUN

**TV-004 · Brake actuator response**: Not affected (confidence high)
- Recommended next step: No action required for this change.
- Evidence: Linked to VCU-BRK-03
- Evidence: Comment notes 'Different measurement clock'
- Evidence: Workshop notes state brake and torque latencies use different clocks
- Requirement link: VCU-BRK-03 (valid) · Previous result: PASS (88 ms)

**TV-005 · Sensor failure: wheel speed**: Not affected (confidence high)
- Recommended next step: No action required for this change.
- Evidence: Linked to VCU-DGN-04
- Evidence: Procedure tests wheel-speed sensor failure
- Requirement link: VCU-DGN-04 (valid) · Previous result: PASS

**TV-006 · Mode event audit trail**: Not affected (confidence high)
- Recommended next step: No action required for this change.
- Evidence: Linked to VCU-LOG-05
- Evidence: Procedure tests mode change logging
- Requirement link: VCU-LOG-05 (valid) · Previous result: PASS

**TV-008 · Legacy diagnostic replay**: Not affected (confidence high)
- Recommended next step: No action required for this change.
- Evidence: Linked to VCU-OLD-88 (unknown requirement)
- Evidence: Comment notes 'Imported row; requirements catalog changed'
- Requirement link: VCU-OLD-88 (unknown_requirement) · Previous result: PASS

**TV-009 · Sport profile torque ramp**: Not affected (confidence medium)
- Recommended next step: No action required for this change.
- Evidence: Linked to VCU-MOD-06
- Evidence: Comment notes 'No quantitative response-time assertion'
- Evidence: Procedure compares Sport vs Comfort torque ramp
- Requirement link: VCU-MOD-06 (valid) · Previous result: PASS (trend)

**TV-010 · Pedal signal spike**: Not affected (confidence high)
- Recommended next step: No action required for this change.
- Evidence: Linked to VCU-DR-02
- Evidence: Procedure tests 7 ms pedal spike filtering
- Requirement link: VCU-DR-02 (valid) · Previous result: PASS

**TV-011 · Torque cancellation on braking**: Not affected (confidence high)
- Recommended next step: No action required for this change.
- Evidence: Linked to VCU-BRK-03
- Evidence: Procedure tests torque cancellation on braking
- Requirement link: VCU-BRK-03 (valid) · Previous result: PASS

**TV-012 · Wake-up timing**: Not affected (confidence high)
- Recommended next step: No action required for this change.
- Evidence: Missing requirement link
- Evidence: Comment notes 'Platform startup only'
- Evidence: Procedure tests ECU wake-up timing
- Requirement link: (empty) (missing) · Previous result: PASS (433 ms)

## 4. Method and limitations

Specifications are parsed and compared by code (requirement IDs, word-level diff, numeric changes). The register is parsed by code (link validity, values in free-text results). An LLM then judges every test against the changes, returning a validated JSON structure; code checks it for coverage, invented IDs, approval wording and internal contradictions.

- Statuses, reasons and model-set actions are LLM judgments and can be wrong; check them before acting.
- 'Fix requirement link' is set by the application from the register links, not by the model.
- The model can mark a test 'directly affected' although it read the change as a rewording with the same meaning. The application then changes the status to 'not affected' and says so next to the test (a safety net, not a better model); it relies on the model's reading of the change, which is not evaluated (docs/known_issues.md, issue 1).
- The analysis was evaluated on 7 change scenarios of this register (84 judgments); see docs/llm_evaluation.md.
