# Alert usefulness and response readiness

**SYNTHETIC — no University findings.**

## Observed sample

- notifications: 12
- observed_episodes: 6
- confirmed_duplicates: 4
- reviewed_redundant: 5
- reviewed_useful: 5
- unreviewed: 2
- redundant_share_of_reviewed: 0.5
- explicitly_unowned_episodes: 1
- unknown_owner_episodes: 1
- impacting_episodes: 4
- completed_response_sample_n: 3
- median_action_minutes_completed_only: 4.0

## Episode trace

|Episode|Service|Notifications|Duplicates|Useful action (min)|Response evidence|Owner|
|---|---|---:|---:|---:|---|---|
|ESS-101|ESS|4|2|12.0|observed|assigned|
|ESS-102|ESS|1|0|4.0|observed|assigned|
|IAM-301|IAM|3|2|UNKNOWN|not_observed_by_window_end|unowned|
|IAM-302|IAM|1|0|3.0|observed|assigned|
|RIS-201|RIS|2|0|UNKNOWN|unknown_missing_response_coverage|unknown|
|RIS-fragment|RIS|1|0|UNKNOWN|unknown_missing_response_coverage|assigned|

## Evidence-linked follow-through

### AQ-ESS-101-duplicate_review
Review same-episode repeat policy without suppressing escalation or separate incidents.

Outcome check: Compare confirmed redundant deliveries per episode and incident-detection coverage before/after a reviewed trial.

Evidence: E-ESS-1

### AQ-IAM-301-duplicate_review
Review same-episode repeat policy without suppressing escalation or separate incidents.

Outcome check: Compare confirmed redundant deliveries per episode and incident-detection coverage before/after a reviewed trial.

Evidence: E-IAM-1

### AQ-IAM-301-routing
Resolve missing or unknown response ownership with an evidenced routing rehearsal.

Outcome check: Measure unowned episodes and time from observed page to first useful action.

Evidence: E-IAM-1

### AQ-IAM-301-runbook
Walk through the actual diagnostic task; record useful steps, stale instructions and missing context.

Outcome check: Compare completion of the same rehearsal task, repair effort and useful-response latency.

Evidence: E-IAM-1

### AQ-IAM-301-escalation
Rehearse escalation with accountable service roles; a document alone is not a tested route.

Outcome check: Record successful handoff and useful action, not just notification delivery.

Evidence: E-IAM-1

### AQ-IAM-301-response_evidence
Reconcile action records with the episode; acknowledgement alone does not establish response.

Outcome check: Retain action evidence and report incomplete/censored episodes beside any latency summary.

Evidence: E-IAM-1

### AQ-RIS-201-routing
Resolve missing or unknown response ownership with an evidenced routing rehearsal.

Outcome check: Measure unowned episodes and time from observed page to first useful action.

Evidence: E-RIS-1

### AQ-RIS-201-runbook
Walk through the actual diagnostic task; record useful steps, stale instructions and missing context.

Outcome check: Compare completion of the same rehearsal task, repair effort and useful-response latency.

Evidence: E-RIS-1

### AQ-RIS-201-escalation
Rehearse escalation with accountable service roles; a document alone is not a tested route.

Outcome check: Record successful handoff and useful action, not just notification delivery.

Evidence: E-RIS-1

### AQ-RIS-201-response_evidence
Reconcile action records with the episode; acknowledgement alone does not establish response.

Outcome check: Retain action evidence and report incomplete/censored episodes beside any latency summary.

Evidence: E-RIS-1

### AQ-RIS-fragment-runbook
Walk through the actual diagnostic task; record useful steps, stale instructions and missing context.

Outcome check: Compare completion of the same rehearsal task, repair effort and useful-response latency.

Evidence: E-RIS-2

### AQ-RIS-fragment-escalation
Rehearse escalation with accountable service roles; a document alone is not a tested route.

Outcome check: Record successful handoff and useful action, not just notification delivery.

Evidence: E-RIS-2

### AQ-RIS-fragment-response_evidence
Reconcile action records with the episode; acknowledgement alone does not establish response.

Outcome check: Retain action evidence and report incomplete/censored episodes beside any latency summary.

Evidence: E-RIS-2

## Source excerpts

**C-ESS** — fictional/export/manifest.md#ess
SYNTHETIC: complete notifications and response records for registration for the declared window; sample selection is not an institutional incident census.

**C-IAM** — fictional/export/manifest.md#iam
SYNTHETIC: complete notification and response export for the declared sign-in window.

**C-RIS** — fictional/export/manifest.md#ris
SYNTHETIC: research notification export begins mid-episode and response records are partial; absence cannot be concluded.

**E-ESS-1** — fictional/registration/incident-101.md#timeline
SYNTHETIC: registration queue delay affected submissions. First page 09:00, acknowledged 09:01, query diagnosis at 09:12. Repeat pages at 09:02 and 09:04 carried no new context. 09:06 escalation successfully reached the database support role. Tested runbook isolated a queue lock.

**E-ESS-2** — fictional/registration/incident-102.md#timeline
SYNTHETIC: next-day queue delay is a separate incident, despite the same rule. First page 09:00, acknowledgement 09:02, diagnostic query 09:04. Service operations owned response and followed the tested runbook.

**E-IAM-1** — fictional/sign-in/cache-warning.md#review
SYNTHETIC: cache warning had no observed user impact. The reviewed route had no accountable role and no escalation destination. First warning and its two repeats supplied no actionable decision. Acknowledged 10:01, but complete retained response log has no useful action before window end. Runbook named an obsolete endpoint.

**E-IAM-2** — fictional/sign-in/incident-302.md#timeline
SYNTHETIC: sign-in errors triggered a page at 12:00. Identity operations diagnosed a dependency fault at 12:03, before pressing acknowledgement at 12:05. The runbook and escalation route were exercised successfully.

**E-RIS-1** — fictional/research/transfer-201.md#retained-notes
SYNTHETIC: delayed research transfers affected submission. Retained pages start 11:00; earlier notifications may be missing. Escalation at 11:15 added a dependency diagnosis. An acknowledgement at 11:10 is retained, but response export is incomplete. Ownership and runbook usefulness have not been established.

**E-RIS-2** — fictional/research/unlinked-warning.md#fragment
SYNTHETIC: 13:00 fragment lacks an incident ticket and impact review. Research platform role is the documented owner. Runbook exists but has not been exercised, escalation is documented but untested, and response records are incomplete.

## Interpretation limits

- Synthetic preparation, not University evidence or findings.
- Explicit episode IDs and retained review establish grouping, never rule fingerprints alone.
- Missing response records are not zero latency; incomplete exports do not prove absence.
- Completed-only response median excludes partial notification history and censored/unknown episodes.
- No incident census: alert recall, fleet reliability and avoided staff costs are not calculated.
