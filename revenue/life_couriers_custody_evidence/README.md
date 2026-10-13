# Life Couriers custody evidence core

Provider-free synthetic acceptance core for one proposed cross-system custody / temperature evidence boundary.

## What it proves

- exact shipment, leg, custody-party, source-system and source-record lineage;
- deterministic multi-leg route continuity;
- required temperature-evidence counts and configured range checks;
- exact event-ID idempotence (retries collapse without a second logical effect);
- fail-closed conflicting event IDs and ambiguous source lineage;
- explicit open exception and timeout-after-commit `UNKNOWN_EFFECT` states;
- reconciliation evidence for unknown effects before a shipment can become `READY_FOR_HANDOFF`;
- order-invariant canonical manifests and offline SHA-256 integrity receipts.

`READY_FOR_HANDOFF` means only that the supplied synthetic evidence satisfies this core's declared completeness/integrity rules. It is **not** a clinical, product-release, regulatory, customs, quality, delivery, or carrier authorization.

## Run

```bash
python -m unittest -v test_rail.py
python -O -m unittest -v test_rail.py
python acceptance.py --require-pass
python -O acceptance.py --require-pass
```

The deterministic acceptance fixture contains 120 synthetic shipments: 100 complete and 20 deliberate holds spanning missing temperature evidence, temperature excursion, unresolved exception, unresolved external-effect uncertainty, and ambiguous source lineage. Input events are shuffled before ingest to exercise out-of-order delivery, and every shipment includes an exact retry.

## Original-demand contract completion

The canonical package also includes a read-only `contract_gate.py` layer for the full Sep. 1 delivery specification that the event rail does not model directly: declared material class, pickup/handoff timing, courier/custodian continuity, lane windows, packout↔sensor lineage, permit/document validity, acknowledged excursion/window incidents, recipient identity and proof of delivery.

```bash
python -m unittest -v test_contract_gate.py
python -O -m unittest -v test_contract_gate.py
python contract_cli.py acceptance
```

That frozen fixture contains exactly 240 synthetic shipments / 720 legs across six service lines: 192 `EVIDENCE_COMPLETE` and 48 `HOLD`, with exactly eight each for custody gaps, packout/temperature mismatch, invalid documents, unacknowledged time-window breach, duplicate/orphan leg graph, and incomplete recipient/POD. Every valid shipment must complete, every defective shipment must hold with its exact stable code, and three full signed fixture reruns must be byte-identical.

`contract_gate.py` emits a canonical SHA-256-bound manifest and supports a caller-injected detached signer that receives only the 32-byte digest. Production signing stays in buyer-controlled KMS/HSM infrastructure. The fixture's deterministic HMAC signer is public synthetic test data only and is not production signing material. Manifest fields explicitly keep dispatch, release, clinical, temperature-disposition and customs authority false/non-inferred.

## Integration boundary

This package has no network client and no credentials. An integration may translate buyer-owned event records into the strict event schema, but external side effects remain outside this core. Receipt hashes provide tamper-evident integrity only; the contract layer can attach a buyer-controlled detached signature without storing private key material. Neither layer authorizes dispatch, clinical/material classification, patient decisions, temperature disposition, customs judgment, shipment release, provider mutation, deployment, contract acceptance, payment, or recognized revenue.
