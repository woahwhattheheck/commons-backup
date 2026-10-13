# ASTRA-FLOORDRAIN — floor-sale capacity relief

Research-only, default-OFF V4 mechanism packet in the sole canonical `main:candidates/v4` tree.

## Why this seam exists

The pinned official reference engine blob is `3c202c7ee921da239356789e266b694635103fc4`. Three interpreter facts compose:

1. unit actions run before market orders;
2. a successful `SELL` at the `$1` price floor removes one unit from the private shed and pays `$1`, but **does not** increment public market inventory; and
3. at end of day, actor inventories are transferred to the shed only until `shedCapacity` is full; the remainder is discarded in deterministic actor/item insertion order.

Therefore, when capacity pressure is real and cannot be solved by existing CARRYBANK-style temporary inventory hoisting, a floor-price sale can act as a non-price-poisoning emergency drain: release a shed slot before EOD so a more valuable imminent cargo unit is retained instead of discarded.

This packet does **not** claim that the situation is common in current native play or that the policy is profitable in a held-out game. It does not activate anything.

## Ownership boundary

- CARRYBANK owns temporary actor-inventory hoisting of near-term consumables.
- HARVESTCLOCK / SELLWINDOW own sale-window semantics and runtime sale wiring.
- Product owners (MELON, FERT, etc.) own product-specific economics and reserves.
- FLOORDRAIN owns only the cross-product fallback: floor-only liquidation strictly for shed-capacity relief / EOD retention.

No controller, evaluator, runtime key, default, archive, workflow, Kaggle submission, or production source is changed here.

## Candidate

`floor_capacity_relief.py` provides:

- `project_eod_drop(...)`: a pure, prefix-preserving projection of official EOD shed transfer/discard ordering;
- `plan_floor_capacity_relief(...)`: a fail-closed planner that considers only items whose supplied current quote is exactly `$1`, respects per-item protected minima and remaining market-row budget, and chooses the best positive cumulative prefix of otherwise-discarded incoming cargo; and
- `verify_engine_blob(...)`: Git-blob authentication against the pinned official engine source.

The declared-value admission rule for a marginal freed slot is:

`incoming_retention_value + $1 realized cash - drained_shed_shadow_value`

Because EOD retention is prefix-ordered, preserving a later discarded unit requires making room for every earlier discarded unit. The implementation evaluates cumulative prefixes rather than sparsely cherry-picking later cargo.

Unknown shed shadow value defaults to infinity (never drain). Unknown incoming value defaults to zero. Above-floor quotes are out of lane.

## Executed focused receipt

Executed in the session Python runtime:

```text
python -m unittest -v
17 tests, 17 passed, 0 skipped
python floor_capacity_relief.py > EVIDENCE.json
python -m json.tool EVIDENCE.json
```

SHA256 after the passing run:

```text
c05b5937074d50e0de5296058d6b3ca8cfd781b307d42ca441e9a576dd6ea76f  floor_capacity_relief.py
3e8ad428f3375009c1b76cbd28643d18f32f4c5cc7797615957596c88134723a  test_floor_capacity_relief.py
22b54e2c5506fb70fadd0edd063e02f87c28c4d95ac4bfcd57a7c1d79159758e  EVIDENCE.json
```

The positive synthetic witness starts with a full 100-unit shed, two MELON units due to arrive at EOD, and two unprotected MILK units at a supplied floor quote of `$1`. Baseline loses both MELON. FLOORDRAIN emits one `SELL MILK 2` market row, records `$2` floor cash and zero market-inventory delta, then projects both MELON retained. The declared witness gain is `+494` under deliberately explicit scenario values (`MELON=250`, `MILK shadow=4`); that number is **not** a native-game score claim.

Negative controls refuse to act for: no projected overflow, above-floor sale quote, non-positive declared value, exhausted market-row budget, or fully protected floor cargo.

## Reproduce

From this directory:

```bash
python -m unittest -v test_floor_capacity_relief.py
python floor_capacity_relief.py
python floor_capacity_relief.py --engine ../../../../reference/engine/kaggriculture.py
```

The optional `--engine` form exits nonzero unless the supplied file Git-blob hashes to the pinned official engine blob.

## Promotion gate

Before any runtime activation, a later owner must source-census the current composed native routes and show naturally reachable capacity-loss cells, then run both-seat/current-native opponent gates. Required evidence includes prevented discarded units, retained-value realization, market-row displacement, reserve/feed/service regressions, market inventory delta, and terminal own/rival margin. If those cells are absent or economics are negative, keep this packet as a falsification/boundary artifact only.
