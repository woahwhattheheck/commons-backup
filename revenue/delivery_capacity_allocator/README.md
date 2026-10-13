# Delivery Capacity Allocator

`tjlabs.delivery-capacity-allocation/v2` is a buyer-neutral, offline post-acceptance capacity diagnostic for scarce service delivery windows. Version 2 is intentional: the prior v1 receipt shape/semantics could imply operational currentness from caller-supplied roots, so the fail-closed authority contract is not silently published under the old schema.

Commons already tracks one deal truthfully and can prioritize pre-sale pursuits. This package solves a different problem: multiple individually valid accepted/funded deals must not all be planned against the same bounded delivery capacity. It consumes a capacity-policy generation, a deal-demand generation, and an active-reservation generation, conserves active reservations first, then deterministically computes whole-slot diagnostic candidates.

## Allocation contract

Only explicit `BUYER_ACCEPTED` and `FUNDED_TO_START` rows compete for diagnostic capacity. Existing active reservations consume slot units before new work is considered. Corrupt known-slot reservations still consume their claimed units before HOLD so bad lineage or service metadata cannot accidentally free capacity.

New capacity is never proposed into a slot that has already started. A future `accepted_at`, an ended active reservation, an orphan active reservation whose deal disappeared from the current demand generation, overdraw, unknown slot, service mismatch, duplicate active reservation, or identity rebinding fails closed. Orphan/corrupt known-slot reservations remain capacity-consuming while the global state is held.

Priority remains deterministic: `FUNDED_TO_START` before `BUYER_ACCEPTED`, then earliest deadline, earliest acceptance time, and stable deal ID. Input array order does not change the semantic diagnostic allocation or `allocation_sha256`; the outer receipt remains bound to exact raw source bytes.

A positive per-deal diagnostic result is named `DIAGNOSTIC_CAPACITY_CANDIDATE`, never `ALLOCATED_FOR_OWNER_REVIEW`. It also carries `DIAGNOSTIC_ONLY_NO_OPERATIONAL_AUTHORITY` in its reasons. The output deliberately avoids an operational-sounding allocation label that a downstream consumer could detach from the receipt-level HOLD.

## Trust boundary: hashes are integrity, not authority

This source package has **no independently authenticated retained-root host adapter**. The `--policy-sha`, `--demand-sha`, and `--reservations-sha` arguments prove only that the bytes match the caller's expected bytes. They do not prove that the caller supplied the complete/current authoritative generations.

Accordingly:

- `compile_bytes()` owns current process UTC; it exposes no caller clock override.
- Source-local current compilation always includes `INDEPENDENT_ROOT_AUTHORITY_REQUIRED` and can only emit a HOLD state. It cannot self-mint `CURRENT`.
- `compile_historical_bytes(..., evaluated_at=...)` exists only for deterministic replay/diagnostics and always emits `HISTORICAL_REPLAY_ONLY`.
- `verify_historical_bytes()` proves exact historical receipt integrity only.
- `verify_current_bytes()` owns current process UTC and fails closed while independent root authority is unavailable.

A future operational host may consume the diagnostic core only after it independently reacquires/authenticates the exact policy, demand, and reservation generation roots. That host boundary is intentionally not simulated by a caller-constructed `TrustedStore`, candidate hash, environment variable, or self-signed receipt.

## Authority ceiling

Every receipt keeps buyer contact, schedule commitment, provider send, payment mutation, contract acceptance, staffing commitment, deployment, and revenue recognition authority false. `DIAGNOSTIC_CAPACITY_CANDIDATE` is a computed capacity candidate, not operational authority, not an allocation, not a buyer promise, and not an external reservation.

## CLI

```bash
python -m revenue.delivery_capacity_allocator.cli compile \
  --policy policy.json --demands demand.json --reservations reservations.json \
  --policy-sha <sha256> --demand-sha <sha256> --reservations-sha <sha256> \
  --out allocation.json

python -m revenue.delivery_capacity_allocator.cli verify \
  --policy policy.json --demands demand.json --reservations reservations.json \
  --policy-sha <sha256> --demand-sha <sha256> --reservations-sha <sha256> \
  --receipt allocation.json
```

`compile` writes the process-current diagnostic packet but returns the nonzero HOLD exit code until an independent authority adapter exists. `verify` likewise cannot return `VERIFIED_CURRENT` from source-local caller-supplied roots.

Inputs remain bounded strict UTF-8 JSON with duplicate/non-finite rejection. CLI reads stable regular-file generations and writes create-exclusively without pathname cleanup that could delete foreign replacements.

## Validation

```bash
python -m py_compile revenue/delivery_capacity_allocator/*.py
python -m unittest -v revenue.delivery_capacity_allocator.test_engine
python -O -m unittest -v revenue.delivery_capacity_allocator.test_engine
```

The fix-forward regression suite covers caller-clock removal, self-derived-root non-authority, v1-to-v2 receipt separation, diagnostic-only positive labels, historical-vs-current separation, expired/started slots, future acceptance, orphan reservations, conservative capacity consumption under corrupt service metadata, replay/tamper, strict JSON, and filesystem output refusal.
