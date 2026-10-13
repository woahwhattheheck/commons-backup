# Sixty Vines Tap-to-Table Integrity Rail — synthetic delivery core

This package is the offline, deterministic delivery core behind the **Sixty Vines San Antonio / La Cantera Tap-to-Table Integrity Rail** offer. It turns an approved synthetic event ledger into a content-addressed reconciliation receipt. It is intentionally **not** a POS integration, guest system, inventory writer, payment processor, alcohol-service decision engine, or production deployment.

## What it proves

The core models the operating lineage that must remain attributable across 60 taps:

`approved wine/SKU -> keg/lot -> tap/line -> cleaning/status -> pour-size -> table/check -> synthetic monetary/inventory effect`

It fails closed before recording a synthetic effect when it sees:

- an unknown tap, keg, lot, or line;
- a SKU assigned to the wrong tap;
- a keg not assigned to the named tap;
- a line that is on HOLD/CLEANING or whose cleaning evidence is missing/overdue;
- insufficient keg volume;
- an exact-effect retry under a different event ID;
- a duplicate pour ID;
- a refund/void conflict or refund above the remaining reversible amount;
- a timeout/unknown-effect state that has not been explicitly reconciled.

Exact duplicate event retries are deduplicated by full canonical event bytes. Reusing an `event_id` with different bytes is a hard replay error. Input order does not matter: unique sequence numbers define the canonical ledger order, so shuffled copies of the same ledger produce the same state and receipt hashes.

## UNKNOWN_EFFECT contract

`POUR_UNKNOWN` records the intended synthetic effect but applies **no** inventory or monetary change. While that ambiguity is unresolved, a later pour sharing the pending effect's tap, line, or keg fails closed with `UNKNOWN_RESOURCE_BLOCK`; unrelated resources remain available. Reuse of the pending effect ID is also blocked by the effect ledger.

A later `RESOLVE_POUR` must say exactly one of:

- `APPLIED` — apply the stored intended effect once; or
- `NOT_APPLIED` — close the ambiguity without applying it.

`RESOLVE_POUR` is the only path that can clear that pending resource quarantine. This is the fail-closed timeout-after-commit boundary: the package never guesses or permits a dependent effect to pass through unresolved inventory ambiguity.

## Acceptance generator

`rail.py acceptance` deterministically creates the full synthetic acceptance ledger:

- **20,000 unique events**
- **60 configured taps**
- periodic line-cleaning evidence
- pours across every tap
- waste events
- refund lineage
- timeout/unknown-effect events followed by explicit reconciliation
- no external calls

The locally proven receipt committed with this package reports:

- 20,000 processed / unique events
- 60/60 taps with accepted pours
- 18,294 applied synthetic effects
- 0 holds
- 0 unresolved unknown effects
- receipt SHA-256 `ee0ccafe168f4d4504f0c54cb18680558469e96bc1bd6ac5b5a72edcc00f8f41`

Those values are a **synthetic regression result**, not a buyer acceptance, production result, alcohol/inventory/payment effect, or recognized revenue.

## Run

From the repository root:

```bash
python -m unittest discover -s revenue/sixty_vines_tap_integrity -p 'test_*.py' -v
python -O -m unittest discover -s revenue/sixty_vines_tap_integrity -p 'test_*.py' -v
python -m py_compile revenue/sixty_vines_tap_integrity/rail.py \
  revenue/sixty_vines_tap_integrity/test_rail.py \
  revenue/sixty_vines_tap_integrity/test_rail_hardening.py

python revenue/sixty_vines_tap_integrity/rail.py acceptance \
  --events 20000 \
  --taps 60 \
  --receipt /tmp/sixty-vines-acceptance.json \
  --require-pass

python revenue/sixty_vines_tap_integrity/rail.py verify-receipt \
  /tmp/sixty-vines-acceptance.json
```

A passing acceptance run requires:

1. zero holds;
2. zero unresolved unknown effects; and
3. pours on every configured tap.

The offline receipt verifier fails closed unless the receipt has the exact v1 evidence shape, required types and digest forms, internally consistent summary/coverage/hold/unresolved-effect invariants, and a matching canonical SHA-256 binding. That checksum is an integrity mechanism, **not a digital signature or an identity/authentication claim**.

## Test coverage

The package currently contains **33 hostile regression tests** across `test_rail.py` and `test_rail_hardening.py`, covering:

- valid pour inventory/money accounting;
- exact retry dedupe;
- conflicting event-ID rejection;
- duplicate effect-ID suppression;
- wrong-line, lot mismatch, unavailable-line, overdue-cleaning, and insufficient-volume holds;
- waste as inventory-only effect;
- partial refund, refund cap, void, and refund/void conflict rules;
- UNKNOWN_EFFECT apply / not-applied / retry-block behavior;
- resource-scoped pending ambiguity quarantine and release after explicit reconciliation;
- continued progress on unrelated taps while another resource is quarantined;
- shuffled-input deterministic replay;
- duplicate sequence rejection;
- invalid line status and duplicate line configuration;
- exact 20,000-event / 60-tap acceptance;
- generator byte determinism;
- exact-v1 receipt validation and rejection of rehashed malformed/hash-only receipts;
- offline CLI receipt verification;
- hostile negative and boolean amount rejection.

The same tests are run in normal Python and under `python -O` so safety rules do not depend on `assert`.

## Hosted regression gate

`.github/workflows/sixty-vines-tap-integrity.yml` runs the normal and optimized suites, compile gate, full 20,000-event / 60-tap acceptance, and receipt verification whenever this package or its workflow changes on a push or pull request.

## Explicit boundary

This package does **not**:

- ingest guest names, contact information, ages, or other guest PII;
- verify age or authorize alcohol service;
- choose wines, pairings, menus, pricing, comps, refunds, or service decisions;
- call, write, or mutate a POS, payment processor, inventory system, reservation system, tap controller, or provider account;
- service or clean a line;
- initiate inventory movement or monetary movement;
- deploy anything;
- establish regulatory compliance, production readiness, buyer acceptance, a contract, booked revenue, or payment.

A real implementation would require buyer-approved schemas, system boundaries, roles, source-of-truth rules, cleaning/status policy, POS/inventory/provider adapters, identity/access controls, independent security/operational validation, golden fixtures, and signed human acceptance.