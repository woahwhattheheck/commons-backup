# Contractor transition -- handoff evidence (UIOWA-108)

**This scenario is fictional.** Every person, application, service identity,
runbook and change record below was invented for rehearsal. It is not a
University of Iowa finding and not a statement about University access
practice. No real account data appears in it, and the packet is refused
outright if any is found.

Packet `UIOWA-108-SYNTHETIC-TRANSITION-001`. Departing: `SYN-PERSON-001`.

## Where the transition stands

| State | Items | What it means |
| --- | ---: | --- |
| COMPLETED | 2 | a dated change record with an evidence locator confirms it happened |
| UNRESOLVED_OWNERSHIP | 2 | still owned by the departing contractor, no successor recorded |
| NO_EVIDENCE | 2 | no record establishes either outcome |

**Transition NOT closed — 4 item(s) remain open.**

There is no completion percentage here on purpose. One unresolved
service identity is a contractor who still has a way in; averaging it
against completed items would produce a reassuring number that
describes nothing anybody can act on.

## Items

### COMPLETED

**SYN-APP-001** — Course Fee Reconciler (fictional) (`applications`, ESS)

- SYN-CHG-001 recorded REASSIGN_OWNER on 2026-09-15
- Evidence: `synthetic://uiowa-rfq18649/108/change-record-001`
- Next: None. Retain the evidence locator for the closeout record.

**SYN-SVC-001** — syn-svc-reconciler (`service_identities`, ESS)

- SYN-CHG-002 recorded ROTATE_CREDENTIAL on 2026-09-16
- Evidence: `synthetic://uiowa-rfq18649/108/rotation-log-001`
- Next: None. Retain the evidence locator for the closeout record.

### UNRESOLVED_OWNERSHIP

**SYN-APP-002** — Vendor File Loader (fictional) (`applications`, ESS)

- still owned by the departing contractor and no successor is recorded
- Next: Name an accountable owner before the contractor's last day. This is a live gap, not a paperwork gap.

**SYN-RB-002** — Vendor file failure triage (fictional) (`runbooks`, ESS)

- still owned by the departing contractor and no successor is recorded
- Next: Name an accountable owner before the contractor's last day. This is a live gap, not a paperwork gap.

### NO_EVIDENCE

**SYN-RB-001** — Nightly reconciliation restart (fictional) (`runbooks`, ESS)

- SYN-CHG-004 is marked COMPLETED but carries no evidence locator
- Next: Ask for the change record or the system export that would settle it. Do not record an outcome without one.

**SYN-SVC-002** — syn-svc-vendorload (`service_identities`, IAM)

- successor SYN-PERSON-003 is named but no completed change record shows the handoff occurred; a named successor is a plan, not evidence
- SYN-CHG-003 is REQUESTED, not complete
- Next: Ask for the change record or the system export that would settle it. Do not record an outcome without one.

## Still UNKNOWN (University inputs not collected)

- the real joiner/mover/leaver process and who authorises each step
- whether service identities are inventoried anywhere authoritative
- how contractor end dates reach the access-management system, if they do
- what evidence the University can actually export for a completed revocation
- who owns a runbook when its author leaves
