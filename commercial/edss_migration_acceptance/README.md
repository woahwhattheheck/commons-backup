# EDSS migration/interoperability acceptance evidence

`commercial.edss_migration_acceptance` is a provider-free acceptance harness for disease-surveillance modernization work. It is deliberately **not** an EDSS, an epidemiology engine, a clinical rules system, an HL7/FHIR certification suite, or a security/compliance attestation tool.

Its job is narrower and commercially useful: given synthetic/deidentified or separately approved **opaque IDs and hashes**, prove whether a declared source export, target export, and interface-event set reconcile exactly enough for a human implementation team to review migration/cutover evidence.

The public package never needs patient names, DOBs, addresses, diagnoses, conditions, lab results, clinical notes, or raw HL7/FHIR payloads. Rows contain only caller-supplied identifiers, field IDs, and value hashes. The compiler rejects email/phone-shaped IDs and unknown payload keys; it does not prove identifiers are deidentified. Callers remain responsible for supplying synthetic or previously deidentified opaque IDs. Interface evidence contains only envelope identifiers, sequence numbers, timestamps, payload hashes, and acknowledgement metadata.

## What it checks

### Migration snapshots

Each source/target snapshot binds:

- stable snapshot ID;
- role (`SOURCE` or `TARGET`);
- schema revision;
- capture time in canonical UTC seconds;
- complete-export declaration;
- exact record count;
- canonical SHA-256 of normalized rows.

A row contains a stable opaque record ID and a nonempty set of `field_id -> value_sha256` entries. The compiler classifies the union of source, target, and independently retained expected IDs as:

- `PARITY_OK`
- `MISSING_TARGET`
- `UNEXPECTED_RECORD`
- `EXPECTED_SOURCE_MISSING`
- `FIELD_MISMATCH`
- `DUPLICATE_SOURCE`
- `CONFLICT_SOURCE`
- `DUPLICATE_TARGET`
- `CONFLICT_TARGET`

Duplicate rows are not silently collapsed. Exact duplicates and conflicting reuse of the same canonical ID are distinct findings.

### Independent expectation observation

The expectation object is a separate evidence boundary. It binds the retained source snapshot ID + source digest, exact expected record-ID set, and exact expected interface-event set with order-invariant digests.

The compiler can verify the observation is internally bound, fresh, and consistent with the supplied source snapshot. It **cannot authenticate the external system that minted the observation**. Production adapters must obtain that authority independently; a caller-written expectation is not transformed into provider truth by this library.

### Interface acceptance

Observed interface events are payload-free envelopes:

- interface ID;
- message ID;
- logical record ID;
- source sequence;
- event time;
- received time;
- payload SHA-256;
- bounded acknowledgement list (`ack_id`, time, `ACKED|REJECTED`).

The compiler detects:

- exact replay duplicates;
- same message ID reused with conflicting event identity/payload;
- unexpected or missing expected events;
- event references to unexpected logical records;
- non-monotone source sequence in receive order;
- equal receive timestamps on distinct same-interface events (fail closed; source sequence is not a receive-order tie-break);
- missing acknowledgements;
- duplicate acknowledgement IDs within one event or reused across events/messages;
- multiple acknowledgements where the acceptance contract expects one;
- rejected acknowledgements;
- impossible receive/ack chronology;
- stale/future event evidence;
- events outside the declared cutover interval.

The cutover interval is half-open: `start <= event_at < end`. Exact start is included; exact end is excluded.

This is transport/evidence reconciliation. It does not prove semantic HL7/FHIR conformance or public-health correctness.

## Receipt states

- `ACCEPTANCE_READY` — complete source/target exports, fresh and bound expectation, every record at parity, every expected event observed exactly once with one ACK, no contradictions.
- `EVIDENCE_INCOMPLETE` — a source or target export is explicitly not complete.
- `EVIDENCE_STALE` — otherwise valid evidence exceeds the declared freshness policy.
- `MIGRATION_MISMATCH` — migration row reconciliation has one or more findings.
- `INTERFACE_MISMATCH` — migration is clean but interface acceptance has one or more findings.
- `HOLD` — structural/binding/chronology/future-evidence contradiction that should not be downgraded into a normal mismatch.

A state is not vendor acceptance, State acceptance, production readiness, award, payment, or recognized revenue.

## Determinism and replay

The compiler normalizes rows, field sets, expectations, and observed event ordering before hashing. Receipt JSON is canonical and byte-stable for the same normalized packet, policy, and trusted `as_of`.

`verify` recompiles from the exact receipt `as_of`. That proves the **historical receipt** is untampered; it intentionally does not claim that old evidence is still fresh today. A current operational decision requires a new compile from current approved/provider evidence.

## CLI

The production CLI captures current UTC internally; there is no production backdating flag.

```bash
python -m commercial.edss_migration_acceptance.cli compile \
  --input commercial/edss_migration_acceptance/fixtures/synthetic_ready.json \
  --json-out /tmp/edss-receipt.json \
  --md-out /tmp/edss-receipt.md

python -m commercial.edss_migration_acceptance.cli verify \
  --input commercial/edss_migration_acceptance/fixtures/synthetic_ready.json \
  --receipt /tmp/edss-receipt.json
```

Input files must be bounded regular files. Outputs are create-exclusive ordinary files; existing outputs and final-component symlinks fail closed.

## Public synthetic fixture

`fixtures/synthetic_ready.json` is wholly synthetic. Its apparent source/target rows contain only three opaque records and hashes of invented strings. Its three interface events are invented envelopes. The fixed proof receipt in `fixtures/synthetic_ready_receipt.json` was compiled at the fixture's frozen acceptance time and is suitable for deterministic offline verification, not a current provider assertion.

## Verification

```bash
python -m unittest commercial.edss_migration_acceptance.test_acceptance -v
python -O -m unittest commercial.edss_migration_acceptance.test_acceptance -v
python -m py_compile commercial/edss_migration_acceptance/*.py
```

The hostile suite covers clean parity, missing/unexpected/mismatched/duplicate/conflicting rows, incomplete exports, stale/future evidence, source/expectation binding, event omissions/extras/replay/conflict/order, missing/rejected/duplicate/multiple ACKs, chronology, cutover boundaries, order invariance, duplicate JSON keys, non-finite JSON, bool/int traps, unsafe timestamps/hashes/IDs, raw-payload-shaped unknown fields, receipt/policy/input drift, create-exclusive output, and symlink refusal under normal and optimized Python.

## Authority ceiling

The package performs no network calls and carries no provider credentials. It has no authority to:

- access or mutate a production EDSS;
- receive or persist PHI/PII;
- make clinical, epidemiological, reportability, diagnosis, or case-management decisions;
- certify HL7/FHIR, security, privacy, accessibility, legal, or regulatory compliance;
- contact a buyer/vendor, register a portal, submit a proposal, sign, quote on another party's behalf, spend, deploy, or recognize revenue.

See `SOUTH_DAKOTA_TEAMING.md` for the current commercial use case that motivated this reusable core.

## Live cash

Verified product pages only — no invented Stripe links.
- [$199 dealer diagnostic](../../dealer-service-lead-rescue.html)
- [$199 referral diagnostic](../../referral-intake-completeness.html)
- [$199 repair diagnostic](../../repair-booking-preflight.html)
- [$199 plant diagnostic](../../plant-downtime-handoff.html)
