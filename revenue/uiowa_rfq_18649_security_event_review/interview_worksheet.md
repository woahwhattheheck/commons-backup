# UIOWA-060 — Security-event evidence worksheet

Use this worksheet during artifact review and interviews. It is practice-focused and is not a compliance audit.

## A. Event selection

| Question | Evidence to request | Interpretation guardrail |
|---|---|---|
| Which event classes are intentionally security-relevant? | Selection rules, use cases, routing configuration, review charter | Presence in logs alone does not establish security relevance |
| Who owns selection/rule maintenance? | Owner record, change history, review cadence | A named team is not evidence that rules are current |
| How are new applications/integrations added? | Onboarding checklist, service inventory, recent onboarding example | Absence from a sample does not prove absence from production |

## B. Retained context and access

Capture whether a reviewer can reconstruct: actor, target, action, source, correlation identifier, service, and time. Request metadata and representative excerpts—not credential values or unnecessary sensitive payloads.

Ask who can access the relevant evidence, how access is approved/reviewed, and how coverage continues when staff change.

## C. Review ownership

For a representative sample, record:

- event identifier and service;
- security relevance: true / false / unknown;
- review owner role;
- review timestamp;
- decision state;
- evidence reference for the decision.

A collected event with no review record is **review evidence missing for that sample**, not proof that no review occurred.

## D. Escalation

Where escalation is required, request the trigger, route, recipient role, timestamp, and linked case/incident evidence. Distinguish a documented escalation rule from evidence that a particular event was escalated.

## E. Action and closure

When a decision requires action, capture action owner, status, completion timestamp, verification step, and evidence reference. “Ticket created” and “action completed and verified” are different evidence states.

## F. Separate general monitoring from security review

Use separate rows when the same telemetry supports service operations and security. For example, CPU saturation may trigger an availability ticket without any security-review obligation, while an identity event may enter a security review workflow. Do not count the former as security coverage unless local evidence establishes that routing.

## G. Candidate measures — only after semantics are fixed

Potential descriptive measures include selected-event volume, reviewed-event count, escalation count, action-open count, and time between recorded stages. Before comparing periods or teams, establish population, start/stop clocks, exclusions, severity/relevance definitions, service boundaries, missing-data treatment, and denominator.

No target, peer percentile, or maturity score is supplied by this worksheet.
