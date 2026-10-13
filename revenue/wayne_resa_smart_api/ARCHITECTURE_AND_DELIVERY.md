# Proposed SMART integration architecture and delivery

Status: **PROPOSED_NOT_ACCEPTED**. This design accompanies the offline acceptance
lab. It is not a deployed architecture, a confirmed SMART interface contract, or a
commitment by Wayne RESA, a prime contractor, or TJLabs.

## Start from the existing system and recovered scope

The recovered RFP describes an on-premises SMART environment using SQL Server and
.NET MVC, with business rules distributed between application code and database
objects. Its scope spans HR/financial integrations, AWS data operations, and
document workflows. The API protocol and payload choices are part of the proposed
solution rather than published endpoint specifications. See
[REQUIREMENTS.md](REQUIREMENTS.md), sections B–D, and the primary sources in
[SOURCE_REGISTER.md](SOURCE_REGISTER.md).

Discovery must establish which existing component owns each business rule before
an endpoint is implemented. A new adapter must not bypass a rule merely because
a direct database write is technically possible. The proposed default is to call
an approved business-service boundary and keep database access behind a documented
contract. Where that boundary does not yet exist, the prime and client must agree
its transactional behavior, permissions, and migration before delivery starts.

## Components and responsibilities

| Component | Proposed responsibility | Required client-specific decisions |
| --- | --- | --- |
| Consumer interface | Versioned contracts; authenticated requests; explicit validation and structured errors | Actual consumers, authentication mechanism, scopes, protocol and payload standard |
| SMART service adapter | Map approved operations to existing business rules; preserve transaction boundaries | Endpoint inventory, stored-procedure/service ownership, approved writes and concurrency behavior |
| Request journal | Bind operation identity to payload digest and recorded outcome; distinguish safe retry from uncertainty | Idempotency-key scope, retention, collision behavior, durable store and recovery ownership |
| Event delivery | Carry correlation IDs and bounded retry history; park unresolved deliveries for review | Event ordering, replay window, timeout classification, status-query capability and dead-letter ownership |
| Reconciliation | Compare approved expected and observed effects with exact monetary units and visible discrepancies | Actual ledger model, precision/currency rules, control totals and discrepancy resolution authority |
| Data pipeline | Separate extraction, transformation and publication with observable checkpoints | Approved AWS resources, residency, schedules, throughput, backup/restore and cost limits |
| Document adapter | Preserve document identity and metadata through routing and indexing | Supported repositories/formats, retention, redaction and permission rules |
| Operations and audit | Record deployment/configuration identity, correlation, outcomes and controlled recovery | Log redaction, retention, alert recipients, support windows and incident ownership |

The API can remain stateless at the request-serving layer while the external
journal keeps durable operation history. Request-local memory is not a substitute
for a durable idempotency record in a real integration. The offline lab models
the history explicitly; it does not supply that production store.

## Retry and uncertain outcomes

An idempotency key must identify a business operation within an agreed scope.
Matching keys with different payloads must be refused or investigated, never
silently accepted as the original operation. Matching duplicates should return a
recorded outcome without adding another business effect, subject to the actual
provider's contract and retention window.

A request known to have failed **before dispatch** can be retried within a bounded
budget. A timeout after dispatch does not prove that the operation failed. The
proposed journal puts that request into an uncertain state until a permitted
status observation resolves it. A generic server error is not, by itself,
permission to resend a financial mutation.

The RFP requires exponential backoff for failed webhook delivery (D.3.c, p.9)
and endpoint documentation including idempotency headers (G.2.b, p.12). It does not
establish mutation-retry permission, a SMART commit-query endpoint, or key semantics.
Consequently, the lab's
logical delays, observation types and state names are proposed acceptance
fixtures. They are not API methods asserted to exist in SMART. A real design must
document what happens when a status query is unavailable or also fails.

Financial reconciliation must preserve the identity of every discrepancy. A +1
cent and a −1 cent discrepancy cannot disappear merely because their aggregate
is zero. Unknown commit state, unauthorized access, and inconsistent amounts each
need a visible outcome and an assigned recovery path. Neither retries nor human
review should silently modify the evidence history.

## What the offline delivery establishes

The lab consumes the unchanged `../wayne-smart-api/` synthetic reconciliation
shadow and its frozen 150-state fixture. It adds an outer, deterministic acceptance
exercise for correlation, retries and recorded uncertainty. Its outputs retain
source identities, input/transcript identities and all visible holds. There are
no SMART credentials, live endpoints, production reads, authoritative writes,
payments, or cloud resources in this exercise.

The inherited shadow's content-envelope digest is a content-integrity mechanism,
not a digital signature or proof of a client's approval. Its 150 states are an
existing synthetic truth set, not a buyer-specified benchmark. New scenario
results must be read together with the implementation's exact execution receipt;
this design document does not declare those tests passed.

The lab is useful for discussing and checking a proposed contract. It does not
prove SQL isolation, distributed exactly-once effects, durable restart recovery
in a live service, actual AWS behavior, throughput, penetration resistance, or
client UAT acceptance. Those remain separate work and evidence.

## Delivery sequence and decision points

| Stage | Concrete output | Exit decision |
| --- | --- | --- |
| 1. Confirm scope | Current addenda, interface/entity catalog, owner map and prioritized workflows | Prime/client agree which operations are in scope and resolve the schedule |
| 2. Specify contracts | Data schemas, error catalog, idempotency/concurrency rules, ledger model and access matrix | Technical owners approve contracts and unresolved cases are listed |
| 3. Build a sandbox vertical slice | One approved operation through the service boundary, journal and observable result | Actual client sandbox evidence demonstrates ordinary, duplicate and uncertain outcomes |
| 4. Extend and validate | Remaining prioritized interfaces, pipelines/documents, automated suites and UAT scripts | Source-linked requirements have evidence; material defects remain visible |
| 5. Rehearse release and handover | Backup/restore and cutover rehearsal, runbooks, training and ownership transfer | Client approves release, rollback authority and support arrangements |

These are dependency-ordered stages, not promised calendar dates. The RFP's
implementation schedule is internally inconsistent and its original award
assumption predates the amended bid deadline. Do not convert those dates into a
new delivery promise without the current solicitation and buyer clarification.

The RFP's coverage, documentation, walkthrough, handover and warranty obligations
are recorded in [REQUIREMENTS.md](REQUIREMENTS.md), section G. Local test counts do
not establish coverage percentages. Delivery would require measurement against
the agreed production codebase and explicit acceptance evidence.
