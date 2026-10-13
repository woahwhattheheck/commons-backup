# TITAN W08 — phase-ordered shed-capacity ledger

This directory contains a small, fail-closed physical-inventory oracle for the
W08 production-throughput lane. It is **not** a second policy and it does not
choose crops, workers, routes, prices, or market strategy. A producer transform
supplies an observed/selected own-event tape; the oracle says which inventory
transitions actually complete and whether an additive job preserves every
retained physical completion.

## Why this exists

The engine resolves all unit actions before market orders at a step, then runs
the end-of-day inventory drop after market. Those boundaries matter:

* `DROP` and `EOD_DROP` destroy carried overflow.
* shed-adjacent `PLACE` leaves unplaced units carried.
* `SELL` can create capacity only after the same step's unit actions.
* `BUY_PRODUCT` or `BUY_ANIMAL` can consume that newly freed room before a later
  deposit.

A blanket “any PLACE or DROP means unsafe” guard misses safe work. For example,
a retained `PLACE` can fill the shed, a guaranteed retained `SELL` can free one
slot, and a later worker can deposit one harvested unit without changing any
baseline event. Removing the sale—or adding an intervening buy—makes the exact
same proposed job destructive. The ledger distinguishes those cases by replaying
phase-ordered quantities rather than relying on aggregate capacity.

## Interfaces

`simulate_capacity(...)` executes a bounded tape and returns per-event receipts,
state snapshots, discard accounting, and a per-item conservation check.
Supported operations are `HARVEST`, `PICKUP`, `PLACE`, `DROP`, `SELL`,
`BUY_PRODUCT`, `BUY_ANIMAL`, `CONSUME`, `EOD_DROP`, and `PASS`.

`admit_additive_events(...)` executes the retained baseline and the combined
baseline-plus-candidate tape. It admits only when:

1. every retained event realizes and discards exactly the same number of units;
2. every named candidate event completes with zero discard; and
3. discard does not increase for any item.

Callers remain responsible for proving the tape itself: route reachability,
action legality, available harvest/stock, affordability, exact market order,
branch identity, and any sale-fill assumption. The optional per-event
`available` bound lets the caller cap a requested operation by those external
facts.

## Verification

From this directory:

```bash
python3 -B -m unittest -v
python3 -B -m py_compile capacity_ledger.py test_capacity_ledger.py test_engine_parity.py run_witnesses.py
python3 -B run_witnesses.py --output WITNESSES.json
```

The same proof runs on pull requests through
`.github/workflows/titan-w08-capacity-throughput.yml`, which retains the test
log, deterministic witness output, and SHA-256 inventory as a workflow artifact.

The suite covers 24 named tests. The model-level contracts enumerate 5,184
post-market-room states and 880 same-unit-stage ordering states. A separate
differential suite executes 2,211 DROP, PLACE, PICKUP, market BUY/SELL, EOD, and
intervening-sale cases against the checked-in official interpreter, whose exact
Git blob is pinned. Together these cover 8,275 deterministic state transitions.
The generated witness JSON records the positive intervening-sale case and the
no-sale, buy-refill, and retained-PLACE counterexamples. These are deterministic source-level fixtures, not full games
or a playing-strength estimate.

## Canonical integration boundary

The immediate consumer is a producer-owned job screen such as the existing
redundant-hire harvest/deposit proposal. Convert only known selected events to
ledger rows, preserve their exact within-phase order, bind market quantities to
an executable fill/affordability proof, and require additive admission before
reporting a completed job. Do not use the ledger to invent sales, reorder market
rows, infer opponent-private state, or credit future cash.

## Contest product (titanmcp)

Live judge pad (≠ Commons Shared Pad / ≠ Commons `/mcp`): https://webmcp-pad.vercel.app/ — **titanmcp 1.4.5**, 24 tools, Agent Resources, `syncConsents`. Board: [titanmcp.html](../../../titanmcp.html). Cite Latch Pad KEEP.
