# Huntington Room–Spa–Dining Guest-Promise Integrity Rail — delivery core

This directory is an **offline synthetic acceptance core** for the commercial offer sent on 2026-09-13. It is not buyer acceptance, a production hotel integration, a booking engine, a payment rail, a guest-contact system, or a claim that the $460,000 implementation has been contracted.

## What the core proves

`rail.py` reconciles opaque promise/journey identifiers across room, spa, dining and bar booking effects; resource availability/maintenance state; room-to-venue handoffs; folio deposits/charges/voids/refunds; gift-card and package balances; timeout-after-commit unknown effects and explicit resolution; and service-recovery state. Operation IDs are idempotency keys: exact retries collapse to one effect and conflicting retries fail closed.

Applied reservations on unavailable resources and simultaneous reservations for the same resource/slot are surfaced as named human-review holds. Unknown booking or monetary outcomes remain explicit `UNKNOWN_EFFECT` holds until a later resolution event. Folio reversals cannot exceed the referenced applied charge/deposit, and gift-card/package redemptions cannot drive balances negative.

`acceptance.py` deterministically generates 15,000 synthetic guest journeys spanning all 143 room identifiers plus spa, dining and bar resources, retries, no-shows, refunds, gift-card/package activity, maintenance hold/release, service recovery and three deliberately unresolved timeout-after-commit monetary effects. The acceptance proof requires all expected surfaces to be represented or explicitly held and produces a canonical content-addressed manifest.

## Authority and privacy boundary

All authority flags are hard-coded false. The core does not choose rates, allocate real rooms/tables/treatments, initiate or reverse money, contact guests, approve service recovery, or connect to PMS/POS/spa/restaurant/payment systems. Guest PII fields are rejected recursively. Buyer schemas, identity/RBAC, production adapters, operational signing keys, real guest/payment data, deployment controls and signed buyer acceptance remain outside this synthetic core.

The commercial email described “signed state.” This package intentionally does **not** fake an operational digital signature: `PACKAGE_MANIFEST.json` records `cryptographic_signature_implemented=false`. It provides deterministic SHA-256 content-addressed manifests/receipts only; buyer-controlled signing is a later integration requirement.

## Run

```bash
python3 -m unittest revenue/highgate_huntington_guest_promise_rail/test_rail.py -v
python3 -O -m unittest revenue/highgate_huntington_guest_promise_rail/test_rail.py -v
python3 revenue/highgate_huntington_guest_promise_rail/acceptance.py --journeys 15000 --output /tmp/highgate-acceptance.json
python3 revenue/highgate_huntington_guest_promise_rail/rail.py build /tmp/highgate-acceptance.json --manifest /tmp/highgate-manifest.json --receipt /tmp/highgate-receipt.json
python3 revenue/highgate_huntington_guest_promise_rail/rail.py verify /tmp/highgate-manifest.json /tmp/highgate-receipt.json
```

Two clean reconciliations of the same logical event set produce identical manifest bytes; modified manifests fail receipt verification.
