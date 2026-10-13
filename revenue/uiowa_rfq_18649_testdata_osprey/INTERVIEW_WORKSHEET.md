# Test-data assessment worksheet

**Status: editable preparation instrument; not completed University evidence.**
Use group-level roles and service context. Avoid unnecessary names, student
records, research records, credential values, and production data exports.

## Session and evidence context

| Field | Entry |
|---|---|
| Session/reference ID | TO COMPLETE |
| Assessment cut-off and evidence period | TO COMPLETE |
| Group and sampled service | TO COMPLETE |
| Participant roles; several roles may share one session | TO COMPLETE |
| Delivery/interface context | TO COMPLETE |
| Artifact references and locators | TO COMPLETE |
| Known sampling limitations | TO COMPLETE |
| Stated practice versus observed example | TO COMPLETE |
| Unresolved disagreement or missing evidence | TO COMPLETE |

## Review the complete lifecycle

| Practice | Question and useful evidence | Record |
|---|---|---|
| Purpose | Which important behavior is this fixture intended to exercise? Show the requirement or interface revision. | Statement / artifact / unknown: ___ |
| Representativeness | Which data partitions, boundaries, and service variants were selected? Which were deliberately omitted and why? | Selection rationale and limitation: ___ |
| Creation | How are examples produced? Demonstrate synthetic creation or explain the controlled origin without supplying sensitive values. | Method, owner role, evidence: ___ |
| Expected behavior | Who confirmed the expected results against a rule independent of the implementation's output? | Contract and review reference: ___ |
| Versioning | Can a past run be reconstructed using its exact fixture, generator, application, and interface versions? | IDs/digests and missing links: ___ |
| Refresh triggers | What happens after a rule, interface, or sample limitation changes? Show a completed recent example. | Trigger, affected fixtures, result: ___ |
| No-change review | Has review ever reasonably concluded that no regeneration was necessary? | Review rationale, not invented refresh: ___ |
| Execution | Show actual results from a test environment. Are generated expectations clearly separate from observations? | Run/adapter/environment references: ___ |
| Maintenance effort | What effort covers preparation, refresh, checking, and cleanup? What is uncertain or dependent on others? | Low–high hours, assumptions: ___ |
| Ownership continuity | What happens when the maintainer changes roles or leaves? Who can reconstruct the process? | Role, successor process, evidence: ___ |
| Retirement | Which obsolete fixtures remain in use? How were dependent services identified? | Retired version and dependencies: ___ |
| Cleanup/retention | Is there a completed cleanup record or explicit retention exception? A schedule alone is insufficient. | Disposition, owner role, evidence: ___ |
| Follow-through | Which improvement is proportionate to the observed limitation and available capacity? | Action, role, effort, success evidence: ___ |

## Record one fixture

| Field | Entry |
|---|---|
| Fixture ID and version | ___ |
| Definition digest and generator version | ___ |
| Source and target interface revisions | ___ / ___ |
| Behavior contract and exact reference | ___ |
| Planned data partitions/boundaries | ___ |
| Known exclusions and impact on confidence | ___ |
| Last completed refresh and evidence | ___ |
| Separate no-change review and rationale | ___ |
| Actual application-run evidence, or UNKNOWN | ___ |
| Maintainer role and effort range | ___ |
| Retirement/replacement/cleanup disposition | ___ |
| Corroborating or contradictory artifacts | ___ |

## Worked fictional reading at 2026-09-19

| Fixture | Metadata observation | Supportable interpretation | Useful next action |
|---|---|---|---|
| ESS-TERM | Fresh recorded date, owner role and reference pointer; five planned boundaries. | No selected metadata follow-ups. Actual application confidence remains unassessed. | Inspect the referenced record and an application run before drawing a practice finding. |
| ESS-LEGACY | Owner unknown; source/target labels differ; old refresh; no refresh pointer; two boundaries omitted. | Several maintenance questions exist. Neither breakage nor inadequate University practice has been demonstrated. | Identify ownership, compare the interface change, review omitted before/after boundaries, and collect a completed refresh example. |
| RIS-FUNDING | Target interface version unknown. | Compatibility cannot be judged from the supplied metadata. | Establish the actual target revision and behavior contract. |
| RIS-RETIRED | Retirement effective; missing cleanup/retention disposition after the example interval. | Follow-up needed on retired data; do not infer deletion or continue counting it as an active-refresh failure. | Obtain a cleanup record or justified retention exception and identify dependent users. |
| IAM-CONTRACTOR | Complete selected metadata; five planned role-window boundaries. | A reference example exists; actual entitlement propagation or revocation has not been tested. | Review real propagation semantics and the independently observed test result. |
| IAM-UNKNOWN | Date, role, evidence pointer, and effort missing. | These remain unknown rather than a fabricated low maturity rating. | Ask one grouped clarification request for the missing maintenance records. |

## Improvement record

Use one record per distinct improvement, with links to every affected fixture
rather than counting a shared maintenance change separately for each service.

```text
Improvement ID:
Observed limitation and evidence:
Affected fixtures / services:
Proposed practice change:
Responsible organizational role (not a staffing commitment):
Effort range and assumptions:
Dependencies / unresolved questions:
Evidence that implementation occurred:
Evidence that it improved testing usefulness:
Reason to defer, when appropriate:
```

Example proposal: create a shared refresh record format that captures fixture
version, target interface, trigger, changed bytes, expectation review, and
application-run reference. Its value should be judged by whether another
practitioner can reconstruct a sampled test and understand its limitations,
not by the number of templates created. Effort and adoption depend on the
existing delivery workflow and must be estimated from that context.
