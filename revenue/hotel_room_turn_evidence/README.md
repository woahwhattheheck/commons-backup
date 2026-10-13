# Hotel Room-Turn Evidence Pilot

Repair/finalizer: **Swarm Z / Z-Helix — GPT-5.6 Sol Pro**

This directory is the fulfillment carrier for a **$2,500 fixed-price, one-property, seven-calendar-day** hotel room-turn evidence pilot. It is deliberately offline and de-identified. It turns bounded housekeeping, maintenance, and manager-release observations into deterministic per-room `READY` or `BLOCKED` receipts. It does not write to a PMS, handle guest records, dispatch staff, charge anyone, or recognize revenue.

## Decision contract

A room is `READY` only when all three required evidence classes are clean for the same room and current turnover generation:

1. fresh housekeeping clearance;
2. fresh maintenance clearance; and
3. fresh release by a manager named in the retained policy.

Everything ambiguous fails closed. Missing evidence, stale evidence, future timestamps, same-timestamp conflict, explicit blocks, wrong-turn evidence, and unauthorized manager release produce `BLOCKED` reason codes. An old turnover cannot clear a new one. Exact duplicate event replay is idempotent; the same `event_id` with changed content is rejected.

## Two distinct claims

The tool intentionally separates two questions that must not be conflated:

- **Historical integrity** — `verify-history` checks that a stored report still matches a separately retained report receipt and the retained policy root. It makes no claim that the evidence is fresh now.
- **Current readiness** — `verify` and `render` first authenticate that historical receipt, then require the exact evidence set bound by it and recompute every decision at verifier-owned current UTC. A previously `READY` room therefore becomes `BLOCKED` after its evidence TTL expires.

There is no perpetual readiness certificate.

## Retained authority

Production policy identity is verifier-owned:

- the policy lives at `fixtures/policy.json`;
- the compiler pins its canonical SHA-256 in `RETAINED_POLICY_SHA256`;
- production CLI commands provide no `--policy` or `--expected-policy-sha256` option;
- production CLI commands provide no `--now` or `--as-of` option.

A caller cannot rewrite the manager allowlist, freshness windows, room/turn scope, or commercial values and then bless that rewrite with a matching caller-selected root. Changing the retained policy requires a reviewed source change that updates both the policy bytes and the pinned root.

Retained policy SHA-256:

`a09f5c8ddb99a4531f1b1770c64737e8780aa1a2d491acbf206d9cd5f1d1472e`

## Frozen synthetic proof

At trusted test time `2026-09-13T15:30:00Z`, the fixture produces **2 READY / 4 BLOCKED**:

| Room | Expected | Reason |
|---|---|---|
| 101 | READY | three fresh, clear, same-turn signals |
| 102 | READY | same, plus an exact duplicate manager-event replay |
| 103 | BLOCKED | housekeeping block and missing manager release |
| 104 | BLOCKED | stale housekeeping |
| 105 | BLOCKED | conflicting maintenance observations at the latest timestamp |
| 106 | BLOCKED | manager release exists only for the wrong turnover generation |

That fixture is a test/replay artifact, not a perpetual live demo. At real current UTC, its evidence correctly ages to `BLOCKED`.

## Run the hostile proof

```bash
cd revenue/hotel_room_turn_evidence
python -m py_compile contracts.py engine.py compiler.py test_compiler.py
python -m unittest -v test_compiler.py
python -O -m unittest -v test_compiler.py
```

The suite covers retained-policy root custody, caller-rewritten policy rejection, TTL expiry, current replay, historical/current claim separation, evidence binding, room/turn scope binding, input-order determinism, exact replay deduplication, conflicting replay rejection, stale/future/conflicting/wrong-turn/unauthorized evidence, duplicate JSON keys, bool/int aliasing, unknown fields, embedded tamper, attacker resealing against a retained receipt, authority drift, exclusive output, symlink refusal, CLI clock/policy override refusal, and normal/optimized byte equivalence at a trusted instant.

## Production-shaped CLI flow

```bash
cd revenue/hotel_room_turn_evidence
rm -f /tmp/hotel-room-turn-report.json /tmp/hotel-room-turn-current.md

REPORT_SHA=$(python compiler.py compile \
  --evidence fixtures/evidence.json \
  --out /tmp/hotel-room-turn-report.json)

# Integrity of the historical artifact only; no current-readiness claim.
python compiler.py verify-history \
  --report /tmp/hotel-room-turn-report.json \
  --expected-report-sha256 "$REPORT_SHA"

# Authenticate history, require the exact bound evidence, and replay at current UTC.
python compiler.py verify \
  --report /tmp/hotel-room-turn-report.json \
  --evidence fixtures/evidence.json \
  --expected-report-sha256 "$REPORT_SHA"

python compiler.py render \
  --report /tmp/hotel-room-turn-report.json \
  --evidence fixtures/evidence.json \
  --expected-report-sha256 "$REPORT_SHA" \
  --out /tmp/hotel-room-turn-current.md
```

Input reads reject symlinks and changing/non-regular files. Output creation is exclusive and will not overwrite an existing pathname.

## Evidence references and operational boundary

`source_ref_sha256` values are references to separately retained source artifacts. They do not prove that a PMS or any external system authenticated those artifacts. A paid engagement must define the source object committed by each digest and retain it independently.

This carrier grants no authority for PMS writes, guest-data access, staff dispatch, guest communication, charges, refunds, booking changes, payment capture, or revenue recognition. Live-system integration, production credentials, expanded scope, and recurring operation require separately written authorization, scope, and price.
