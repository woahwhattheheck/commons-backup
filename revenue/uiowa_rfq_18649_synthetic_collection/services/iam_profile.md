# SYNTHETIC — Identity and Access Management analogue

> **SYNTHETIC EVIDENCE — FICTIONAL AIS-LIKE SCENARIO. Not University of Iowa evidence or a finding.**

## Operating context

This fictional shared platform operates authentication, identity lifecycle events, federation, and privileged workflows. The invented technology shape is Go/Java services, directory and federation adapters, an event bus, policy service, and replicated data store. Roles include a service owner, security engineering lead, on-call rotation, and explicit change authority.

Fictional constraints are high availability, cross-service blast radius, and strict change traceability.

## Canonical facts

| Fact | Area | State | Synthetic observation |
| --- | --- | --- | --- |
| IAM-SW-001 | software development | STRENGTH | Normal changes preserve request-to-deployment traceability. |
| IAM-SW-002 | software development | GAP | Two emergency changes restore service but only one has follow-up review evidence. |
| IAM-SEC-001 | security | STRENGTH | Joiner/mover/leaver samples link authorization to downstream completion. |
| IAM-SEC-002 | security | STRENGTH | Privileged changes require MFA and generate audit records. |
| IAM-OPS-001 | deployment/operations | STRENGTH | The sign-in service has availability/latency objectives and alert ownership. |
| IAM-OPS-002 | deployment/operations | GAP | A written stateful rollback procedure has no demonstrated recovery evidence. |
| IAM-AI-001 | AI readiness | UNKNOWN | The corpus does not establish AI use in authorization or entitlement decisions. |
| IAM-AI-002 | AI readiness | STRENGTH | Governance prohibits autonomous AI access changes outside human-approved change flow. |

## Interpretation

The scenario separates strong access-control evidence from incomplete emergency-review and recovery evidence. AI non-use remains UNKNOWN unless stronger system evidence establishes it.
