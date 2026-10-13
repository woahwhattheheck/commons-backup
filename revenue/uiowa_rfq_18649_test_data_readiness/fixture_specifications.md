# Fictional boundary-case fixture specifications

All identifiers and records in this document are fictional. They are designed to exercise the assessment method without reproducing University data.

## ESS — registration boundary fixture

**Fixture ID:** `ESS-REGISTRATION-BOUNDARIES`  
**Purpose:** Exercise rules and transitions around course registration.

Documented boundary cases:

| Case | Fictional setup | Expected behavior to verify | Maintenance trigger |
| --- | --- | --- | --- |
| add/drop deadline | Student attempts a change immediately before and after a fictional deadline | The workflow distinguishes allowed and disallowed transitions and preserves the reason | Academic-calendar rule or interface change |
| maximum credit load | Student attempts to add a course at and above a fictional credit threshold | The workflow produces the expected decision or approval path | Rule change |
| waitlist to enrolled | A fictional seat opens for a waitlisted student | State transition and downstream notification/integration events remain coherent | Registration workflow or event-contract change |

Assessment question: can the team show why these cases were selected, when they were last refreshed, and which current interface version they exercise?

## RIS — award synchronization fixture

**Fixture ID:** `RIS-AWARD-SYNC`  
**Purpose:** Exercise fictional sponsored-award status synchronization.

Documented boundary cases:

| Case | Fictional setup | Expected behavior to verify | Maintenance trigger |
| --- | --- | --- | --- |
| pending award | Award remains pending while an upstream attribute changes | Integration does not silently promote the record | Status-model change |
| sponsor type variation | Two fictional sponsor categories drive different metadata | Mapping remains explicit and testable | Code-table or contract change |
| resubmission after change | A changed fictional proposal is resubmitted after prior review | Version/status history remains distinguishable | Workflow or API change |

The checked-in rehearsal intentionally omits two of these cases and identifies an older fixture interface version so the evaluator has evidence-backed gaps to report.

## IAM — role transition fixture

**Fixture ID:** `IAM-ROLE-TRANSITION`  
**Purpose:** Exercise fictional identity events through role/employment transitions.

Documented boundary cases:

| Case | Fictional setup | Expected behavior to verify | Maintenance trigger |
| --- | --- | --- | --- |
| contractor termination | A fictional contractor reaches an end date | Downstream access-removal event path is represented | Identity-event contract or lifecycle change |
| role change | A fictional staff member changes job role | Old and new entitlement-driving attributes are represented | Role model or mapping change |
| emergency access expiry | Time-bounded fictional elevated access reaches expiry | Expiration/revocation behavior is represented | Emergency-access process change |

The checked-in rehearsal intentionally lacks ownership and refresh evidence. Those conditions remain **UNKNOWN**; they are not described as failed maintenance. It also omits two cases from its own documented requirement set, which is an **OBSERVED_GAP**.

## Representativeness rule

The assessment never asks whether a fixture is "representative" in the abstract. It asks:

1. what business or integration behavior the fixture is intended to represent;
2. which boundary cases were explicitly selected;
3. what evidence establishes that those cases are still relevant;
4. what important cases are knowingly excluded; and
5. what maintenance effort is required to keep the fixture useful.

This keeps conclusions tied to documented expectations rather than inventing universal coverage requirements.
