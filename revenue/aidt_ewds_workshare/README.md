# AIDT EWDS — offline migration and integration workshare

**Internal engineering surface, not a customer destination or a prime bid.**
Original implementation: Z-Sol. V2 recovery: ZZ-KESTREL-M7Q2.
Operation: `AIDT-EWDS-INTEGRATION-TEAMING-ZSOL-20260917`.
Parent work record: Commons issue #15852; implementation carrier: PR #15866.

This Python 3.10+ standard-library package compares supplied record manifests,
checks supplied Salesforce/Adobe LMS/EWDS event observations, and produces a
replayable workshare packet. It performs **no network transport, migration,
scheduling, source authentication, customer contact or external submission**.
The original callable names remain available; `python -m` now supplies an operator
interface rather than requiring custom integration code to exercise the package.

The source context in [SOURCE.md](SOURCE.md) is retained from the original public
packet copy. The recovery did not verify current portal amendments or deadlines.
Before any external reliance, re-read the controlling Alabama Buys record. A
technical test pass does not establish prime qualifications, registration, partner
interest, buyer acceptance, award, payment or revenue.

## Manifest replay, not a checksum-only summary

`reconcile_migration(source_records, target_records)` accepts two arrays of:

```json
{"record_id":"synthetic-id","record_sha256":"64 lowercase hexadecimal digits"}
```

The V2 receipt retains both complete, sorted ID/digest manifests. Verification
recomputes counts, manifest digests, missing/extra/mismatched IDs and the decision
from those manifests before comparing the complete canonical receipt. Changing a
summary and recalculating its checksum cannot erase a missing record.

`MIGRATION_RECONCILED` requires identical **nonempty** manifests. Differences produce
`HOLD_MIGRATION_RECONCILIATION`. Two empty manifests produce the separately visible
`NO_RECORDS_TO_RECONCILE`: mathematical equality is not positive migration evidence.
Duplicate IDs or invalid records are input errors, not quietly deduplicated data.

This is consistency verification, **not independent provenance**. A caller can
supply different, internally consistent manifests and generate a different valid
receipt. `verify_migration_receipt` optionally accepts independently retained
`expected_source_manifest_sha256` and `expected_target_manifest_sha256` pins to
check that it is the intended generation. A pin comparison is not a certification
that those records originated in a live system.

Only IDs and digests are accepted, not raw record payloads. **Identifiers themselves
may be sensitive.** `pii_assessment=NOT_PERFORMED` replaces the old unjustified
`contains_live_pii=false` claim. Use synthetic IDs in public examples and private
storage for real identifiers. `raw_record_payloads_included=false` describes the
actual closed schema; it is not a privacy certification.

## Supplied event observations

`compile_sync_receipt(event, observed)` checks the existing source/target system
pair and operation vocabulary, binds the event ID, entity reference, payload
digest and observed target reference, and produces a deterministic idempotency
key. It does not send the event or enforce idempotency in a remote system.

`SYNC_ACCEPTED_EXACT` means the supplied observation says accepted and its supplied
payload digest matches. `evidence_authority=CALLER_SUPPLIED_TARGET_RESULT` remains
visible. A negative observation or digest mismatch produces `HOLD_SYNC_ACCEPTANCE`.

## Current-collection readiness

The V2 policy is explicitly `ALL_SUPPLIED_CURRENT_RECEIPTS`, replacing V1's
at-least-one-success rule. Readiness requires every one of the six named evidence
classes, at least one migration and one sync receipt, and **every supplied current
child** passing its respective condition. Empty migrations do not satisfy it.

Failures stay embedded and are named in `blocking_migration_receipts`,
`blocking_sync_receipts` and `hold_reasons`. Identical child duplicates and conflicting
current observations for one source/target/event ID are rejected. The caller must
select the current collection deliberately; historical attempts belong in a
separately retained history, not silently discarded inside this compiler.

Input collections are copied completely, including nested manifests. Mutating a
caller-owned record after compilation does not rewrite the returned packet.
`verify_readiness` replays the children and all parent semantics.

The strongest result remains `WORKSHARE_READY_FOR_PRIME_REVIEW`. Collection
coverage is caller-selected, **not proof of complete project scope or live cutover**.
Every existing outbound/submission/acceptance/award/payment/revenue authority bit
remains literal `false`; the controlling-source recheck remains literal `true`.

## Operator commands

Use an existing authorized cloud environment, not a new checkout on Bryce's disk.
A fresh temporary directory keeps previous outputs intact:

```sh
WORK=$(mktemp -d)
python -m revenue.aidt_ewds_workshare.demo > "$WORK/packet.json"
python -m revenue.aidt_ewds_workshare verify "$WORK/packet.json" --out "$WORK/verification.json"
```

The demo constructs synthetic inputs and uses the real compiler. Verification
prints `VERIFIED_INTERNAL_CONSISTENCY`, not live-system or source-authenticity proof.
For supplied JSON files, use:

```sh
python -m revenue.aidt_ewds_workshare migration source.json target.json --out migration.json
python -m revenue.aidt_ewds_workshare sync event.json observed.json --out sync.json
python -m revenue.aidt_ewds_workshare readiness evidence.json migrations.json syncs.json --out packet.json
python -m revenue.aidt_ewds_workshare verify migration.json \
  --expected-source-manifest-sha256 ACTUAL_INDEPENDENT_SOURCE_MANIFEST_DIGEST
```

`source.json` and `target.json` contain record arrays. `migrations.json` and
`syncs.json` contain arrays of complete V2 receipts, not filenames or summary
counts. `evidence.json` maps the six `REQUIRED_WORKSHARE_EVIDENCE` names to digests.
Omit `--out` for standard output. Existing output files are refused, not overwritten.
Duplicate JSON keys, non-finite/floating values, malformed UTF-8 and oversized
inputs produce errors before output publication.

**Exit code 0 means computation or consistency verification succeeded, not that
migration/readiness is positive.** Inspect the returned `decision`, `state` and
blockers. A valid HOLD receipt is an intentional successful diagnostic result.
Invalid input, inconsistent receipts or failed file operations return exit code 2.

Limits: 10,000 records per input manifest; 128 receipts of each child kind; 20,000
retained source+target records across a readiness collection; 16 MiB JSON input
and canonical receipt bounds. This is an in-memory offline implementation in a
trusted Python host, not a streaming migrator or adversarial-host security service.

## Version and execution evidence

Migration, sync and readiness schemas are V2. Legacy V1 receipts must be regenerated
from retained inputs; the missing replay data cannot be recovered from a summary.
No heuristic auto-upgrade promotes a legacy result.

```sh
python -m unittest -v test_aidt_ewds_workshare test_aidt_ewds_manifest_replay test_aidt_ewds_cli
python -O -m unittest -v test_aidt_ewds_workshare test_aidt_ewds_manifest_replay test_aidt_ewds_cli
```

See [RECOVERY.md](RECOVERY.md) and [RECOVERY_PROOF.json](RECOVERY_PROOF.json) for actual
exact-byte execution, the 729-case manifest reference comparison, the 25-case
collection matrix and real CLI subprocess tests. Local execution and hosted
Actions state are separate observations.

## Work still required beyond this component

Issue #15852 also requests sourced requirement-to-owner mapping, migration mapping
and cutover plans, workflow scenarios beyond event consistency, partner qualification
research and commercial workshare material. This implementation does not complete
those deliverables or identify a qualified prime. No portal, partner or buyer action
is authorized by a receipt. Retain separately verified external facts and use the
existing outreach coordination route before any external approach.
