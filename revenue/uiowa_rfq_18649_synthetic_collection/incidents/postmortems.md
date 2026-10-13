# SYNTHETIC — Incident and postmortem examples

> **SYNTHETIC EVIDENCE — FICTIONAL AIS-LIKE SCENARIO. Not University of Iowa evidence or a finding.**

## INC-ESS-021 — stale downstream code table

A fictional planned update left one downstream display using the previous code table for 18 minutes. Service was restored by cache refresh. Actions ACT-ESS-19 and ACT-ESS-20 were later marked closed, but the packet contains no effectiveness measurement. This supports ESS-OPS-002 and demonstrates the difference between action closure and measured improvement.

## INC-RIS-014 — overnight batch interruption

A fictional partner response caused batch processing to stop. Operators followed RB-RIS-BATCH-3: stopped duplicate replay, identified the confirmed sequence boundary, replayed, reconciled counts, and obtained fictional business confirmation. Recorded recovery time is 47 minutes. This supports RIS-OPS-002.

## INC-IAM-031 — authentication-latency event

A fictional dependency slowdown breached the latency objective while availability stayed within objective. Alerts routed to the service on-call, the incident record linked signal to owner to mitigation, and the review adjusted one alert threshold. This supports IAM-OPS-001.

## INC-IAM-032 — migration-rehearsal gap

A review of a fictional planned state migration found a written rollback sequence but no prior evidence of executing the stateful-data restoration path. The fictional release was delayed pending tabletop and non-production exercise. This supports IAM-OPS-002 without asserting rollback would fail.

## Emergency follow-up

The same packet preserves EC-IAM-006 and EC-IAM-007: both restored service, but only EC-IAM-007 links a follow-up review. That controlled contrast supports IAM-SW-002.
