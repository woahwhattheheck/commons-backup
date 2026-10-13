# Facilitator packet: when rollback is not recovery

**All names, transactions and clocks in this packet are fictional.** The six examples
exercise reasoning about records; they do not demonstrate a real team's recovery.
No operational commands are supplied. Use the offline lab, not a live service.

## Facilitation method

Assign four exercise roles: service lead (coordinates a decision), functional owner
(defines acceptable business behavior), data/queue owner (explains retained state and
compatibility), and observer (records claims, evidence and unresolved questions).
These are suggested workshop roles, not actual personnel assignments or approvals.

At each inject, ask participants to state what is known, what remains unknown, and
what observation would support their next decision. Record their answer before showing
the next checkpoint. A participant saying “we have a rollback script” is a statement
about a procedure, not evidence that its recovery has worked. A successful lab result
is still synthetic. Preserve disagreement rather than force a maturity score.

Run `python lab.py examples.json --format markdown` to reveal the answer key. The JSON
format also gives the full action transcript, raw stored rows, accepted event ledger,
and invariant-by-invariant results. A blocked delivery remains explicitly recorded.

## Round A — reversible configuration (R63-CONFIG)

**Opening:** A reader changes from v1 to v2; no data migration or accepted transaction
occurs. The stored records still contain only `units`.

**Inject:** `incompatible_reader`, minute 2: the reader cannot interpret the rows.
Ask whether reverting the reader also requires restoring data. What evidence would
show that the change really was confined to configuration?

**Decision to discuss:** Return the reader to its original compatible interpretation.
**Answer key:** `configuration_restored`, minute 4: all model invariants hold; the
synthetic interval since incident is 3 minutes. Storage never left v1.
**Evidence request:** Versioned configuration diff, observed application versions,
change scope, and business-check results. An observed successful procedure for this
case cannot automatically establish safety for a data-changing release.

## Round B — readable restore, missing writes (R63-SNAPSHOT)

**Opening:** The pool starts at 2. After the snapshot, ESS-001 adds 2 and ESS-002 adds 3.
Both transactions are acknowledged. A snapshot restore returns the projection to 2.

**Inject:** `healthy_but_missing_writes`, minute 6: the service is readable, but the
expected allocation is 7 and both event IDs lack application records.
Ask who knows which transactions were acknowledged, where that record lives, and
whether restoring the same backup could erase the only record of missing work.

**Decision to discuss:** Under the lab's explicit complete-external-log assumption,
replay the retained accepted transactions into the restored projection.
**Answer key:** `log_replayed`, minute 8: observed and expected equal 7, each accepted
event applied once, synthetic interval 4 minutes.
**Evidence request:** Snapshot consistency boundary, retained-log boundary and coverage,
source offsets, reconciliation record, and functional-owner verification. Missing log
coverage means recovery is not established; it does not authorize guessing transactions.

## Round C — migration and queued work (R63-FORWARD)

**Opening:** A v2 producer accepts RIS-001, but the legacy worker cannot interpret its
payload. Storage contracts to v2 and an attempted old-reader rollback is incompatible.

**Inject:** `old_binary_is_not_data_rollback`, minute 6: old runtime does not restore
old schema or make the queued new-format message consumable. Ask which runtime/data/
queue combinations are supported, and how a deferred message is distinguished from
one already applied.

**Decision to discuss:** Compare a tested forward compatibility repair with a rollback
that would require separate data reconstruction. In this example, install compatible
model reader/worker settings and replay the retained event.
**Answer key:** `forward_compatibility_repair`, minute 9: allocation 6, each event once,
synthetic interval 6 minutes.
**Evidence request:** Compatibility matrix covering producer, consumer, reader and stored
format; representative queued messages; data-change reversibility analysis; recorded
exercise results. A written compatibility claim remains unverified until exercised.

## Round D — duplicate replay (R63-REPLAY)

**Opening:** IAM-001 adds 2. A normal duplicate is skipped. A deliberately non-idempotent
retry applies the same event twice.

**Inject:** `healthy_but_double_applied`, minute 6: the projection is readable, but
observed allocation 6 differs from expected 4 and IAM-001 has application count 2.
Ask whether a retry means “not yet applied,” and whether a side effect outside the
snapshot would also be repeated. The lab does not model external side effects.

**Decision to discuss:** Restore a mutually consistent projection/application ledger and
replay with deduplication under the model's assumptions.
**Answer key:** `snapshot_and_idempotent_replay`, minute 10: allocation 4 and count 1,
even after repeated replay; synthetic interval 5 minutes.
**Evidence request:** Stable event identity, atomicity between effect and application
record, retry behavior, and independently verified downstream side effects.

## Round E — mixed-version split views (R63-MIXED)

**Opening:** Expanding storage creates `units` and `quantity`. An old worker changes
only `units`, leaving 5 and 2 respectively.

**Inject 1:** `split_views`, minute 5: a new reader is healthy but sees 2 where the ledger
expects 5. Ask whether schema expansion alone made old writers dual-write.
**Inject 2:** `bridge_refuses_conflicting_fields`, minute 8: the bridge refuses to select
an authoritative value from contradictory fields, and MIX-002 remains unapplied.

**Decision to discuss:** Preserve disagreement and reconstruct from independently retained
accepted events under the lab assumptions, rather than silently preferring the new field.
**Answer key:** `reconciled_dual_representation`, minute 12: both fields equal 6;
`contracted_and_duplicate_safe`, minute 16: v2-only storage remains 6 and duplicate
replay changes nothing. These are different verification checkpoints, not two incidents.
**Evidence request:** Old/new writer inventory, migration ordering, representation
reconciliation, retained event coverage and post-contraction business verification.

## Round F — matching totals, missing individual work (R63-NETZERO)

**Opening:** NET-001 adds 2 and NET-002 releases 2; both are accepted but neither delivered.

**Inject:** `totals_match_but_work_is_missing`, minute 4: observed and expected totals
both equal 2. Ask whether agreement of a total proves all acknowledgments were honored.
**Answer key:** It does not in this model: two event IDs remain unapplied, so the full
recovery conjunction is false and verified recovery time is null. After replay,
`each_event_accounted_for`, minute 6, establishes all model checks with a 3-minute interval.
**Evidence request:** Per-event acknowledgment/application reconciliation, not only a
balance, count, aggregate health signal, or a zero error-rate observation.

## Editable evidence worksheet

Copy one row per material claim. Keep real exercise evidence separate from lab output.

| Field | Fill during the interview or authorized exercise |
|---|---|
| Service, change and environment | UNKNOWN until supplied; identify synthetic versus actual |
| Claim and exact source locator | Procedure section, interview note, execution log or checkpoint |
| Evidence class | Written procedure / participant account / tabletop discussion / observed execution / unknown |
| Runtime and data scope | Reader, producer, worker, schema, queue and shared dependencies |
| Recovery decision | Chosen option, alternatives, accountable organizational role and rationale |
| Acknowledged-work boundary | What was accepted, where recorded, retention and completeness evidence |
| Demonstration record | Exercise date, environment, exact versions, injected condition, actual result |
| Verification | Business invariants checked, evidence reference, performer and independent review |
| Timing | Definition of start and stop, missing timestamps, observation window and uncertainties |
| Unresolved questions | Preserve contradictory or missing evidence without fabricating a negative finding |
| Next improvement | Practice change, owner role, dependencies, estimated effort range and outcome measure |

A readiness conclusion belongs in the canonical assessor and human review, supported
by actual supplied records. No such conclusion is produced by this companion lab.

## Practical follow-ups, offered as preparation estimates

These are original planning ranges for a hypothetical service, not quotes, promised
completion times, findings about Iowa, or commitments by any person.

| Improvement option | Suggested owner role | Dependencies | Illustrative effort | Evidence of benefit |
|---|---|---|---|---|
| Add business checks to an existing rehearsal | Service lead + functional owner | Known accepted-work source and expected behavior | 0.5–2 person-days | Restored service and acknowledged work reconciled independently |
| Document and exercise runtime/data/queue combinations | Application + data/queue owners | Representative supported versions and fictional fixtures | 2–5 person-days | Old/new producer, worker and reader combinations have recorded outcomes |
| Exercise duplicate-safe recovery with consistent snapshot boundaries | Application + platform owners | Stable IDs, stated atomicity and retained event coverage | 3–10 person-days | Repeated delivery and restore/replay preserve per-event effects |

Actual effort can be materially higher where logs, atomicity or ownership are unknown.
Start by establishing those dependencies instead of assigning a confident estimate.

## Completion and handoff

The facilitator can now run every scenario, locate each inject in the report, check the
expected invariant, and carry an evidence request into an interview. Source, fixtures
and regression tests remain editable. Any integration into the common evidence register
must retain `synthetic: true`, scenario/checkpoint IDs and the input digest; it must not
assign a University finding or maturity level from these model observations.
