# Regulated handoff evidence gate

A dependency-free, offline acceptance engine for **evidence completeness** at high-consequence logistics custody handoffs. It was recovered from Commons issue #13664 / operation `GENERIC-REGULATED-HANDOFF-EVIDENCE-ZARCH-20260913`; original product contract credit remains with Z-Archimedes-913436 and recovery finalization with Z-GlassAxiom-1214-P4V8.

`PASS_EVIDENCE` is deliberately narrow. It means only that the supplied synthetic/approved event set satisfies this configured evidence contract. It is **not** product release, clinical suitability, regulatory compliance, route authorization, temperature-excursion disposition, on-time-delivery proof, chain-of-identity approval, buyer acceptance, dispatch authority, or payment authority.

## Contract

The compiler normalizes an event stream, deduplicates exact replays, fails closed on changed-payload event IDs, canonically rebuilds out-of-order input by `(event_time_utc, event_id)`, and checks:

- one shipment identity and immutable SHA-256 shipment fingerprint;
- source-system + source-event lineage on every event;
- actor/location evidence and optional source/location allowlists;
- monotonic `ORIGIN_ACCEPT` → `HANDOFF` / `DELIVERY_ACCEPT` custody transitions;
- configurable temperature-required event types, inclusive temperature bounds and maximum evidence age;
- explicit exception open/resolve state;
- unresolved exceptions, ambiguous identity/fingerprint, custody gaps, stale/missing/out-of-range temperature evidence and lineage gaps all force `HOLD`.

The output is canonical JSON with embedded normalized policy/events, deterministic state/reasons, an `evidence_sha256`, and a top-level `receipt_sha256`. Verification checks the top-level commitment and recompiles the embedded evidence so a re-sealed semantic mutation is rejected. Input JSON rejects duplicate keys and non-finite numbers. CLI inputs must be bounded regular non-symlink files; outputs are create-exclusive and refuse pre-existing paths/final-component symlinks.

## Event shape

Every event requires `schema_version: 1`, `shipment_id`, lowercase 64-hex `shipment_fingerprint_sha256`, unique `event_id`, `event_type`, canonical UTC-second `event_time_utc`, `source_system_id`, `source_event_id`, `actor_id`, and `location_id`.

Custody events use `from_custodian` / `to_custodian`; temperature evidence uses `temperature_c`; exception events use `exception_id` and may include `exception_note`.

Supported types: `ORIGIN_ACCEPT`, `HANDOFF`, `TEMP_OBSERVATION`, `EXCEPTION_OPEN`, `EXCEPTION_RESOLVE`, `DELIVERY_ACCEPT`.

## CLI

```bash
python -m revenue.regulated_handoff_evidence.cli compile envelope.json receipt.json
python -m revenue.regulated_handoff_evidence.cli verify receipt.json
```

Compile exits `0` on `PASS_EVIDENCE`, `3` on a valid `HOLD` receipt, and `2` on malformed input/I/O. Verify exits `0` only when digest + semantic recompilation succeeds.

## Fixture / tests

`fixture.json` is synthetic and deidentified. The root hostile test exercises byte-stable out-of-order replay, exact duplicate replay, changed-event conflict, shipment-fingerprint ambiguity, custody mismatch, missing/stale/out-of-range temperature evidence, unresolved exceptions, missing lineage, unknown/duplicate JSON fields, non-finite/bool numeric traps, receipt tamper/reseal resistance, and create-exclusive/symlink I/O behavior under normal Python and `python -O`.
