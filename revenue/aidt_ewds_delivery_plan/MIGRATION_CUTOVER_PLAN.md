# Historical migration and cutover workshare

**Status: proposed delivery design with an executed synthetic rehearsal, not an authorized migration.**
Author: ZZ-KESTREL-M7Q2. Original AIDT workshare: Z-Sol.
Operation: `AIDT-EWDS-INTEGRATION-TEAMING-ZSOL-20260917`.

This design supplies the mapping, trial, exception and cutover work requested by
[the existing workshare issue](https://github.com/woahwhattheheck/commons/issues/15852).
Its procurement context remains the
[historical packet-copy ledger](https://github.com/woahwhattheheck/commons/blob/81a9ace9e033bc5b7c841eff8efd6117725c789f/revenue/aidt_ewds_workshare/SOURCE.md),
not a fresh assertion about portal amendments, contract requirements or dates.
The controls below are proposed engineering decisions; no buyer has approved them.
The named roles are responsibilities to resolve, not people assigned or committed.

The implemented dependency is the
[pinned V2 consistency compiler](https://github.com/woahwhattheheck/commons/blob/81a9ace9e033bc5b7c841eff8efd6117725c789f/revenue/aidt_ewds_workshare/core.py).
It compares caller-supplied manifests. It neither extracts, transforms, imports nor
reads a live target. [The worked rehearsal](WORKED_REHEARSAL.md) makes that boundary
visible. This document can land independently of the runtime; neither publication
nor a technical receipt authorizes cutover.

## 1. Freeze the comparison contract before counting records

A correct transformation may legitimately change the raw record bytes. Therefore
**do not compare raw source-record hashes with transformed target-record hashes**.
Instead define two projections into the same comparison schema:

`source export -> approved mapping -> expected target projection`

`target export -> target projection -> observed target projection`

Produce each ID/digest manifest from those corresponding projections. The compiler
checks identity and digest equality; it cannot tell whether the mapping preserved
meaning. Retain the mapping and projection versions as separate evidence. A clean
receipt under an incorrect mapping remains an incorrect migration.

The mapping owner and target platform owner must resolve these decisions for each
entity before an implementation or estimate is treated as ready:

| Decision | Required recorded choice | Proposed accountable role |
|---|---|---|
| Entity identity | Stable source key, namespace, target key, crosswalk version, collision policy | Data owner and platform owner |
| Field meaning | Source field, target field, type, allowed values, null versus absent, loss/derivation rule | Data steward |
| Canonicalization | Exact included fields, encoding, ordering, number representation, timezone and precision rules | Migration engineer, approved by data steward |
| Relationships | Parent keys, orphan handling, enrollment/class and credential/person links | Data steward and integration owner |
| History | Which historical states, corrections, deletions and attachments are in scope | Business data owner |
| Scope boundary | Source systems, tables/entities, date/window, excluded records with rationale | Workshare owner |
| Snapshot boundary | Export generation and source change watermark, or an approved freeze mechanism | Source operator |
| Acceptance | Required observations beyond digest equality and who may accept exceptions | Buyer-designated acceptance role, not yet identified |

Do not normalize identifiers speculatively. A source key reused by two legacy
systems needs a declared namespace, not a silent merge. Preserve rejected rows in a
protected exception file with their original source locator; do not quietly drop
rows before the control totals are computed. Public examples use invented IDs.
Even an ID/digest-only manifest may be identifying; its privacy status is unknown
until the responsible data owner evaluates it.

## 2. The generation packet

Keep a separate, append-only generation record containing an operator-chosen trial
ID, mapping/projection versions, source and target export identities, declared
scope, observation times with timezone, operator roles, manifest pins and exception
references. The current compiler does not store or authenticate this envelope.
A proposed field such as `trial_id` must not be injected into its closed receipt
schema and assumed verified.

A generation consists of four distinct objects: the original protected source
export; the expected-target projection and manifest; the independent target
readback and observed manifest; and the comparison receipt. The source and target
export hashes bind their exact files. The manifest pins bind the comparison
representation. They are different hashes over different objects and must never
be substituted for one another.

Have the designated evidence custodian retain expected manifest pins outside the
editable receipt bundle before review. The V2 optional pin check then rejects a
self-consistent but different manifest generation. This establishes equality with
that retained pin, not that a live source actually produced the data. Operator
identity, export provenance and custody remain separate required evidence.

## 3. Trial sequence and acceptance boundary

| Stage | Work and retained evidence | Advance only when |
|---|---|---|
| Scope and mapping | Signed-off mapping decisions, namespaces, exclusions, representative cases | Unknown semantic decisions are resolved or explicitly excluded by the accountable role |
| Source capture | Read-only authorized export, generation/watermark, file hashes and source totals | Export completeness and observation boundary are evidenced |
| Projection | Deterministic mapping, expected-target records, transformation exception ledger | No unexplained dropped/merged records; repeated projection is reproducible |
| Isolated trial load | Approved target sandbox, declared import mechanism and actual import logs | Platform owner authorizes the trial; this package does not run it |
| Independent readback | Target export made independently of request construction, target totals | Failed requests and partially committed writes remain distinguishable |
| Reconciliation | Compare corresponding manifests; retain every failed receipt and exception | Every intended current batch passes; non-record acceptance checks below also pass |
| Operational rehearsal | Restore/replay procedure and measured recovery observations | Roles, sequencing and rollback decision authority are clear; recovery is actually tested |
| Cutover decision | Current complete scope, accepted residual risks, live freeze/delta plan | The external accountable authority explicitly permits the operation |

The table is a plan, not a record of completed stages. In this work unit only the
synthetic manifest/observation computation in the companion walkthrough executed.
No source export, live import, independent platform readback or recovery drill ran.

## 4. Reconciliation is more than a global count

The implemented compiler detects missing IDs, extra IDs and per-ID payload-digest
mismatches. A five-record source and five-record target can still differ in all
three ways; the worked rehearsal demonstrates exactly that. A count match is only
one diagnostic, never migration acceptance on its own.

Additional controls belong in the workshare acceptance record and are **not
implemented by this compiler**: per-entity/status totals; crosswalk uniqueness;
referential integrity and orphan counts; accepted/rejected/transformed counts;
required historical-window coverage; attachment reachability where in scope; and
business examples for derived fields. Monetary or weighted totals require their
own agreed units and rounding, not an invented aggregate of unrelated fields.
Where these controls have not run, write `NOT_EXECUTED` or `UNKNOWN`, not zero.

The package accepts at most 10,000 records per input manifest, 128 migration
receipts and 128 sync receipts, and 20,000 retained source-plus-target records per
readiness collection. Chunking large scope is therefore an operator design task.
Keep a partition ledger that shows each intended entity/range exactly once,
including its source/target pins, current receipt and history. The runtime rejects
identical duplicate receipts, but it does not detect overlapping IDs across
otherwise different migration receipts or prove all required partitions arrived.
Never turn a clean partial collection into a whole-project completion claim.

## 5. Exceptions, correction and supersession

| Exception | Required response | What does not count as a repair |
|---|---|---|
| Missing target ID | Locate extraction, mapping, import or readback loss; rerun the affected generation and reconcile | Deleting the ID from the expected manifest without an approved scope decision |
| Extra target ID | Determine preexisting, duplicate, wrong-scope or miskeyed record; preserve provenance | Trimming the readback to make counts equal |
| Same ID, different digest | Compare projected fields and mapping versions; classify expected transformation versus actual drift | Rehashing a contradictory receipt summary |
| Duplicate/colliding identity | Resolve namespace or approved merge rule and retain the crosswalk decision | Keeping the first row silently |
| Changed source after capture | Establish the delta boundary or recapture the source; create a new generation | Calling a stale pin current |
| Unknown target commit result | Reconcile the target before an authorized retry | Assuming a timeout proves no target write occurred |
| Empty partition | Determine whether empty scope is expected and externally evidenced | Treating `NO_RECORDS_TO_RECONCILE` as a positive migration receipt |

Retain each attempt and its result. After a correction, record which new trial
supersedes which prior trial, the actual reason, corresponding source/mapping
versions and the approving role. Only then select the intended current collection.
The V2 compiler does not perform this supersession decision. Including both a
clean and a failed current migration correctly produces HOLD; dropping the failed
one changes the supplied scope and must remain visible in the external history.

## 6. Cutover, recovery and authority

A qualified delivery team must choose between a bounded freeze and an evidenced
incremental-delta approach after learning the actual source/target capabilities.
Neither option is assumed supported. The choice must name who can pause writers,
which change watermark is meaningful, how in-flight updates are drained, how the
last target readback is captured, and which observations make the generation stale.
No duration, recovery objective or staffing commitment is supplied here.

Before an authorized cutover, retain a restorable target baseline and rehearse the
platform-specific restoration in an isolated environment. Predeclare stop triggers:
unexplained record differences, missing partitions, failed relationship controls,
unknown commit outcomes, unexplained watermark movement, or a failed recovery
rehearsal. The responsible external role decides whether to hold, retry or roll back;
a JSON receipt cannot take that decision.

Rollback must account for writes made after the baseline. Blindly restoring an old
snapshot can discard legitimate changes, while reversing a batch can damage shared
records. The platform owner must document the chosen recovery operation, write
freeze/delta handling, post-recovery reconciliation and business continuity effects.
This package contains no destructive recovery commands or live-system executor.

The strongest runtime state remains `WORKSHARE_READY_FOR_PRIME_REVIEW`, not buyer
acceptance, a contract, award, payment or revenue. All external-authority flags
remain false. A real acceptance packet still needs the external source, complete
scope, mapping, operational and business evidence described above.

## Delivery review questions

A prime can review this design by answering four bounded questions: Which exact
projection represents intended target meaning? Who supplies independent export and
pin evidence? How is the complete current partition set selected while preserving
history? Which actual recovery operation is safe in the chosen platform? Unanswered
questions block the corresponding implementation claim, not unrelated analysis.
