# Salesforce / Adobe LMS / EWDS interoperability workshare

**Proposed logical integration design; no live connector or vendor API is exercised.**
Author: ZZ-KESTREL-M7Q2. Original scope: Z-Sol, operation
`AIDT-EWDS-INTEGRATION-TEAMING-ZSOL-20260917`, [issue #15852](https://github.com/woahwhattheheck/commons/issues/15852).

The historical source copy calls for interoperability and applicant/class
synchronization. It does not establish the installed product editions, APIs,
licenses, authentication scheme, quotas, webhook guarantees or data ownership.
Those remain partner/buyer discovery questions. The directions and controls below
are proposed interface decisions, not claims about existing AIDT systems or vendor
capabilities. No endpoint, permission or retention period is invented.

## 1. One authoritative writer per field

Use the installed source of record as the origin for a given field. Do not enable
bidirectional writes merely because two platforms expose the same label. Record
field ownership, allowed direction, conflict policy and reconciliation projection
before mapping the production interface.

| Logical event | Candidate flow to confirm | Required ownership decision | Existing compiler operation |
|---|---|---|---|
| Applicant identity/profile | Salesforce or EWDS to the approved consumer | Canonical person key, merge policy, permitted shared fields | `upsert_applicant` |
| Class definition | Authoritative class catalog to consuming system | Class ID/version, schedule/state ownership, crosswalk | `upsert_class` |
| Enrollment | Business-authorized origin to LMS | Applicant/class relationship, enrollment state and deduplication key | `enroll` |
| Attendance result | Learning system to the approved workforce record | Attendance semantics and correction ownership | `attendance_update` |
| Credential result | Authoritative credential source to consumer | Credential ID, status, validity/revocation meaning | `credential_update` |

A flow is not approved simply because its pair is accepted by the compiler. The
current code allows distinct pairs among the symbolic names `salesforce`,
`adobe_lms` and `ewds`; these are schema labels, not registered network clients.
Deletion, person merge, class cancellation and credential revocation need explicit
business/interface designs. No unsupported operation should be disguised as an
existing operation to pass validation.

## 2. Identity and payload contract

For each interface, record the source entity key, target reference, crosswalk
version, event identity, event ordering/version rule, mapping version and permitted
payload fields. Use an explicit namespace where keys overlap between systems.
Choose a stable event identity for one logical business change; do not regenerate
it simply because a transport attempt failed. Separate a new correction event from
a retry of the original event.

The implemented event receipt binds `source_system`, `target_system`, `event_id`,
`entity_ref`, `operation` and `payload_sha256`. The supplied target observation binds
`accepted`, `target_ref` and `target_payload_sha256`. Its deterministic idempotency
key hashes the complete supplied event material. That construction means changing
the payload changes the key; a real adapter still needs an explicit rule for a
same-event-ID/different-payload conflict. The readiness compiler rejects two current
observations for the same source/target/event identity, but it is not a durable
remote deduplication store.

Use a versioned canonical payload projection on both sides when comparing meaning.
A digest computed over the outgoing request and copied into the response is not an
independent observation of persisted target state. If a target API cannot expose
that projection, record the narrower available evidence and an unresolved readback
step rather than claiming `SYNC_ACCEPTED_EXACT` proves persistence.

## 3. Proposed adapter state transitions

This state model belongs to a future platform adapter, not to the current offline
compiler. Its successful execution is `NOT_EXECUTED` in this work unit.

| State | Durable evidence | Permitted next decision |
|---|---|---|
| Prepared | Authorized business change, immutable canonical payload, mapping version | Validate scope and permission before dispatch |
| Dispatch attempted | Attempt ID and exact event identity, safe transport metadata | Await an actual result or classify uncertainty |
| Rejected | Target refusal and safe reason code | Correct the business/input defect; do not retry indiscriminately |
| Outcome unknown | Timeout/disconnect or ambiguous response | Query/reconcile the target before deciding on retry |
| Target acknowledged | Actual response and target reference | Obtain independent target readback; acknowledgment is not persistence proof |
| Readback matched | Independently observed target projection matches intended payload | Produce the supplied-observation receipt and evaluate the declared current scope |
| Readback differs | Field-level difference, missing target or wrong generation | Hold, investigate mapping/race/partial write, retain every attempt |
| Superseded | Explicit successor event/trial and reason | Preserve history; evaluate the selected current observation only |

A replayed request should not create duplicate business effects, but that property
must be implemented and tested with the actual target. Do not claim exactly-once
delivery from a deterministic hash. A durable event ledger or supported platform
idempotency facility is a proposed dependency requiring review. It is not provided
by `compile_sync_receipt`.

For transient failures, the adapter owner must choose bounded retries, backoff,
expiry, dead-letter handling and human escalation appropriate to actual vendor
limits and business needs. No numerical retry interval or rate is assumed here.
A credential/configuration denial is not a reason to broaden permissions or bypass
access controls. A business rejection is not necessarily transient.

## 4. History versus current evidence

The companion [worked rehearsal](WORKED_REHEARSAL.md) compares a rejected and an
accepted observation for the same synthetic event. Their idempotency keys match,
but including both as current produces an explicit conflict error. This is useful:
an append-only attempt history and a current-state observation collection answer
different questions and must not be flattened into one list.

Retain attempt history separately with generation, target observation and sequence
or event-version evidence. The operator or adapter must select a current observation
using a defined ordering/supersession rule supported by the actual platform. The
compiler does not inspect timestamps or determine which observation is newest. An
accepted historical attempt cannot hide a currently rejected or divergent event.

Likewise, a clean receipt for one event does not prove applicant/class coverage,
relationship correctness, queue drainage or project completeness. The workshare
owner must reconcile intended events against delivered/readback events and account
for duplicates, exclusions and missing events. Those inventory and ordering checks
remain separate proposed work, not tests silently counted as passed.

## 5. Least-authority integration boundary

Use approved service identities and the minimum operations/records required by the
chosen flow. The actual identity provider, scopes, secret store, renewal and
revocation process must be established by the platform owner. No keys, tokens,
passwords or real applicant data belong in this public workshare.

Operational logging should retain correlation, generation, event identity,
non-sensitive result categories and protected references sufficient to investigate
failures. Whether an identifier is personal data cannot be inferred from its
format. Restrict raw exports, crosswalks and detailed exception records according to
the data owner's actual handling rules; retention/deletion periods are unknown
until that policy is supplied. Avoid logging full payloads by default merely to
make the demonstration look more complete.

The offline compiler does not grant credentials, send messages, change records,
make appointments, invoke vendor services or authorize a proposal. A technical
result must not be repurposed as business or security certification.

## 6. Acceptance work that remains to be run

Require a permitted sandbox and approved synthetic data before live adapter tests.
The acceptance specification should pair normal and failure cases for duplicate
redelivery; timeout after an actual commit; an older event arriving after a newer
one; same identity with a changed payload; rejected input; missing crosswalk;
partial parent/child creation; mismatched readback; and permission revocation.
Expected evidence must name the actual target records and business effects, not
only an HTTP status or locally generated receipt.

Also verify a reconciliation-only recovery path that observes without writing,
followed by an explicitly authorized replay of only unresolved events. A full
queue resend after an ambiguous failure risks repeating completed effects; the
receipt library does not decide whether such a replay is safe.

The current demonstrated capability is narrower: strict supplied-event validation,
deterministic event binding, comparison of a supplied target observation, rejection
of conflicting current observations and replayable parent consistency. The
[original runtime tests](https://github.com/woahwhattheheck/commons/blob/81a9ace9e033bc5b7c841eff8efd6117725c789f/revenue/aidt_ewds_workshare/RECOVERY_PROOF.json)
and the worked rehearsal exercise those actual functions. They do not establish
remote transport, persistence, license fit or business acceptance.
