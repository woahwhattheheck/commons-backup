# Test reliability and feedback investigation

**SYNTHETIC EXERCISE**

Analysis of supplied export only; not University findings, maturity scores, confirmed availability, or release approval.

Observed: 18 attempts / 12 logical test chains.
Input SHA-256: `fb2839980304a1300280ed11edeb850df6ee17c140e485927317fd841f394b0e`

Rates apply only to exported, eligible observations. A retry recovery is not a confirmed flaky test.

| Metric | Numerator | Denominator | Fraction |
|---|---:|---:|---:|
| first_attempt_failure_rate | 6 | 10 | 0.6000 |
| observed_final_pass_rate | 9 | 11 | 0.8182 |
| observed_test_retry_recovery_rate | 2 | 4 | 0.5000 |

| Latency | Observed / eligible | p50 seconds | p95 seconds |
|---|---:|---:|---:|
| queue | 15 / 17 | 10.0 | 1200.0 |
| execution | 16 / 17 | 20.0 | 1500.0 |
| logical_feedback | 8 / 12 | 90.0 | 2700.0 |
| retry_execution | 7 / 7 | 20.0 | 20.0 |

p95 uses nearest rank. Null durations are unavailable, never zero; small samples are descriptive only.

## Prioritized investigation questions

| Priority | Group / service / run / test | Signal | Question | Source references |
|---:|---|---|---|---|
| 1 | ESS / fictional-registration / synthetic-repeat / synthetic-check | repeated_test_failure_unconfirmed | Does the same assertion reproduce on a controlled rerun? Distinguish a product defect from a deterministic test defect. | synthetic:repeat/attempt/1; synthetic:repeat/attempt/2 |
| 1 | IAM / fictional-provisioning / synthetic-changed-input / synthetic-check | unresolved_failure | What missing context or failure evidence would distinguish a defect, instability and an environment change? | synthetic:changed-input/attempt/1; synthetic:changed-input/attempt/2 |
| 1 | RIS / fictional-grant-export / synthetic-defect / synthetic-check | reported_confirmed_defect | What is the linked defect disposition and retest evidence? Confirmation is reported by the source, not verified by this calculator. | synthetic:defect/attempt/1; synthetic:defect/attempt/2; synthetic:triage/defect-01 |
| 1 | RIS / fictional-grant-export / synthetic-runner / synthetic-check | reported_confirmed_infrastructure | What infrastructure correction and follow-up evidence close the linked incident? | synthetic:runner/attempt/1; synthetic:runner/attempt/2; synthetic:triage/runner-01 |
| 2 | RIS / fictional-grant-export / synthetic-slow / synthetic-check | feedback_delay | Where does end-to-end feedback wait: queue, execution or between retries? | synthetic:slow/attempt/1 |
| 2 | RIS / fictional-grant-export / synthetic-slow / synthetic-check | queue_delay | Is runner capacity, concurrency policy or dependency waiting responsible for this observed queue? | synthetic:slow/attempt/1 |
| 2 | RIS / fictional-grant-export / synthetic-unreviewed-recovery / synthetic-check | retry_recovered_unconfirmed | Did code, runner, dependencies or test data change? Compare retained logs before calling this flaky. | synthetic:unreviewed-recovery/attempt/1; synthetic:unreviewed-recovery/attempt/2 |
| 2 | ESS / fictional-registration / synthetic-clock-conflict / synthetic-check | evidence_completeness | Resolve: reversed:queued_at:finished_at, reversed:queued_at:started_at. Missing evidence is not a zero duration or a low maturity score. | synthetic:clock-conflict/attempt/1 |
| 2 | ESS / fictional-registration / synthetic-flaky / synthetic-check | reported_confirmed_flaky | What corrective work and repeatable validation address the linked flakiness diagnosis? Do not count a retry pass as a fix. | synthetic:flaky/attempt/1; synthetic:flaky/attempt/2; synthetic:triage/flaky-01 |
| 2 | IAM / fictional-provisioning / synthetic-cancelled / synthetic-check | evidence_completeness | Resolve: missing:finished_at, missing:queued_at, missing:started_at. Missing evidence is not a zero duration or a low maturity score. | synthetic:cancelled/attempt/1 |
| 2 | IAM / fictional-provisioning / synthetic-changed-input / synthetic-check | evidence_completeness | Resolve: comparison_context_changed. Missing evidence is not a zero duration or a low maturity score. | synthetic:changed-input/attempt/1; synthetic:changed-input/attempt/2 |
| 2 | IAM / fictional-provisioning / synthetic-partial-history / synthetic-check | evidence_completeness | Resolve: attempt_history_incomplete. Missing evidence is not a zero duration or a low maturity score. | synthetic:partial-history/attempt/2 |
| 2 | IAM / fictional-provisioning / synthetic-unknown-clock / synthetic-check | evidence_completeness | Resolve: missing:queued_at. Missing evidence is not a zero duration or a low maturity score. | synthetic:unknown-clock/attempt/1 |
| 3 | IAM / fictional-provisioning / synthetic-partial-history / synthetic-check | incomplete_execution | Was the check intentionally skipped/cancelled, or is completion evidence missing? | synthetic:partial-history/attempt/2 |
| 3 | IAM / fictional-provisioning / synthetic-cancelled / synthetic-check | incomplete_execution | Was the check intentionally skipped/cancelled, or is completion evidence missing? | synthetic:cancelled/attempt/1 |
