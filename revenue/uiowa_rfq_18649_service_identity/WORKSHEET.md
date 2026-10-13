# Service-identity lifecycle interview and evidence worksheet

UIOWA-054 · internal, editable practice instrument · **synthetic rehearsal until an authorized engagement supplies curated metadata**.

## Session frame

Purpose: understand how nonhuman identities remain maintainable across applications, build pipelines, integrations and scheduled jobs. Evaluate organizational practice and service consequences, not individuals. Do not ask for passwords, tokens, private keys, connection strings, secret-store contents, production dumps or unsolicited screenshots containing credentials.

Capture the assessment cutoff, agreed evidence freshness window, evidence custodian, scope of services sampled, organizational roles consulted, important academic/research/business cycles, exclusions and unresolved questions. Proposed sessions and roles are preparation only; they are not appointments or confirmed availability.

Use the same eight dimensions for ESS, RIS and IAM, but allow different workable processes and technology stacks. A single identity may serve multiple groups; record every declared consumer rather than allocating it to one group and losing shared dependencies.

| Dimension | Ask | Request only sanitized metadata | Interpretation and practical follow-up |
|---|---|---|---|
| Purpose | What service need does this identity support? What ordinary business behavior fails without it? | Identity ID, purpose summary, service IDs, representative usage-record locator and observation date. | A meaningful name is not purpose evidence. Missing metadata calls for a one-role inventory review, not an assertion of misuse. |
| Ownership | Which organizational role can explain, maintain and eventually retire it? Has that role accepted responsibility? | Accountable role ID, current acceptance-record locator, role-status metadata. | Named ownership is weaker than a current acceptance record. When the listed role has departed, route reconciliation to the service portfolio owner. |
| Privilege rationale | What functions require the declared scope? How are exceptions and changing needs revisited? | Plain-language scope/rationale, review record ID and specialist role. Never credential values. | Assess the existence and usefulness of the rationale; this instrument does not test authorization or declare exposure. |
| Renewal | When is continued need reviewed? What happens near expiry, including shared consumers and peak periods? | Review due date, expiry metadata if applicable, last human decision locator and date. | An overdue review is a workflow follow-up, not proof that access is inappropriate. Confirm how inclusive dates and non-expiring identities are represented. |
| Continuity | Can another active role use the relevant runbook and records without relying on the former maintainer? | Distinct continuity role, rehearsal date, outcome locator and receiving-role binding. | Written procedures or a ticket saying “handoff done” do not establish a demonstrated rehearsal. Estimate coordinated effort with service owners. |
| Owner transition | What changed when staff responsibilities moved? Did the receiving role accept it? | Former/current role IDs, effective date, receiving-role acceptance reference, revised handoff record. | Evidence before the effective change cannot validate the new arrangement. Preserve destination/current-owner disagreements for reconciliation. |
| Shared dependencies | Which services and jobs still consume it, directly and indirectly? How complete is that inventory? | Declared consumer IDs, dependency links, coverage statement and corroborating record locator. | Empty or incomplete inventory is not retirement clearance. Walk reverse dependencies with service owners; record unobserved links as unknown. |
| Retirement | How is continued need resolved, consumers removed and decommissioning verified? | Human decision, consumer-removal record, inventory coverage, decommission verification locator/date. | A retirement ticket with declared consumers is contradictory. No report output disables an identity or approves retirement. |

## Worked exercises

### A. Shared IAM dependency crosses organizational boundaries

Use `svc-shared`. The fictional directory is consumed by registration and research submission, with research export downstream. Ask the facilitator to follow the dependency direction: an identity consumed by the directory potentially affects those downstream services; an identity consumed only by export does not imply upstream directory impact.

Expected result: four declared affected services, three groups, six applicable dimensions supported, two not applicable. Ask which dependency records establish coverage and what missing consumers would change. Do not present four as a proven complete live impact count.

Useful next exercise: have each service-owning role compare the fictional consumer list with its integration inventory and identify a shared maintenance window. This is an assessment proposal, not a scheduled change.

### B. A new owner inherits an old continuity demonstration

Use `svc-transition`. The former role departs September 1, 2026. The receiving role is current; a written transition procedure is dated September 2. The continuity rehearsal occurred August 25 under the previous arrangement.

Expected result: transition documented; continuity stale. The prior rehearsal is retained as historical evidence, not erased, but it cannot prove continuity after the effective change. Change the transition kind to `record` only when an acceptance record is actually supplied. A fresh rehearsal must bind to the continuity role and occur on/after the change.

Useful next action: receiving-role acceptance plus a tabletop handoff rehearsal covering service purpose, dependencies, review dates and where authorized operators find operating procedures. No participant shares secret values with the assessor. Effort is coordinated, not a cosmetic ownership-field edit.

### C. “Retired” disagrees with declared active consumption

Use `svc-retired-conflict`. A retirement ticket supports the declared retired status, but registration remains listed as a consumer.

Expected result: contradictory retirement evidence. Ask whether the consumer list is stale, a cutover is incomplete, or the ticket describes only one environment. Do not choose an explanation without supporting records. Record the responsible service role, needed consumer-removal evidence and a service-validation step.

Remove consumers only after source reconciliation. Even then, dependency coverage and direct dependency evidence must support that state, and retirement needs its own record. This produces a better-supported assessment; it never performs retirement.

### D. An empty consumer list and no coverage guarantee

Use `svc-retiring-empty` and compare it with `svc-unknown`. The first has a written retirement plan but incomplete consumer coverage. The second lacks basic ownership, purpose and lifecycle metadata.

Expected result: neither is clearance. Separate the effort of reconstructing shared dependencies from a one-role review of missing purpose or lifecycle dates. Avoid a numeric maturity score that hides these different kinds of uncertainty.

## Editable follow-up register

| Identity / dimension | Observed, reported, documented, unknown, stale or conflicting evidence | Service consequence to investigate | Accountable organizational role | Evidence to obtain | Effort estimate and assumptions | Dependencies | Proposed completion evidence |
|---|---|---|---|---|---|---|---|
| Replace with curated ID | Preserve exact evidence state and locator | State as a question until supported | Role, not employee score | Metadata only | Small/medium starting band; agree real effort | Other services/roles/records | Record or demonstrated outcome appropriate to the dimension |

For disagreements, retain both source locators and their dates. Record the resolution rationale outside the runtime inventory before issuing a new version; do not quietly delete inconvenient evidence. A normalized input digest supports reproducibility but does not establish authenticity or permission.

## Capture before closing the assessment discussion

Confirm the actual service/role sample, relevant exclusions and cutoff. Separate public/organizational guidance, supplied practice records, demonstrations and interview reports. Re-read every asserted “observed” result against its evidence IDs. Ask whether approaching renewals or shared dependencies change sequencing. Keep improvement options practice-focused and proportional to operational effort. A proposed improvement is not a commitment, appointment, procurement decision or permission to change a live system.
