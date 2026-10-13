# SYNTHETIC — Operations runbooks and recovery evidence

> **SYNTHETIC EVIDENCE — FICTIONAL AIS-LIKE SCENARIO. Not University of Iowa evidence or a finding.**

## ESS planned-release runbook

The fictional sequence is: confirm approved change set, record artifact/version, capture pre-change health, deploy in the planned window, execute smoke checks, record rollback-versus-forward-repair decision if needed, and capture post-release health. REL-ESS-042 contains each field and supports ESS-OPS-001.

The fictional incident action register lists ACT-ESS-19 and ACT-ESS-20 as closed, but the packet has no measurement showing whether either action improved outcomes after closure. This bounded evidence supports ESS-OPS-002.

## RIS batch-recovery runbook

RB-RIS-BATCH-3 instructs the operator to stop duplicate replay, identify the last confirmed sequence, notify the integration owner, replay from the confirmed boundary, reconcile counts, and record business confirmation. INC-RIS-014 records all steps and a measured fictional recovery, supporting RIS-OPS-002.

An interview says the scheduler must be paused before one schema promotion, but the formal procedure omits that ordering step. The disagreement is retained and supports investigation of RIS-OPS-001.

## IAM service and migration runbook

SLO-IAM-AUTH-1 defines fictional availability and latency objectives and connects alert ownership to the on-call role, supporting IAM-OPS-001. RB-IAM-MIGRATE-2 contains a rollback sequence for a stateful migration, but there is no exercise or incident record demonstrating full data restoration; this supports IAM-OPS-002.
