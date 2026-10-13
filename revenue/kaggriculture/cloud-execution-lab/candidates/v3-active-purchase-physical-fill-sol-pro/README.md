# TITAN V3 active-purchase physical fill — SOL-PRO

Operation: `TITAN-V3-ACTIVE-PURCHASE-PHYSICAL-FILL-20260910-01`

Slack claim: `#titan-kaggriculture`, message `1789069535.090209`.

## Source-proven defect

The canonical frozen-selected seller inherits `SellScheduler.receipt_profile()`.
That callback deliberately runs unit actions against an oversized shed so a
represented DROP cannot hide overflow. It then applies the same oversized rule
to market purchases, adding the full requested quantity of every represented
`BUY_PRODUCT` and `BUY_ANIMAL` row. The official interpreter does not: valid
purchases commit one unit at a time and stop once the real shed reaches
`shedCapacity`.

With capacity 4, three CARROT stored, and an active request for two GOOSE, the
engine can commit at most one GOOSE. The predecessor projection records five
units and can force two CARROT sales before the next represented deposit. The
candidate records the physical upper bound of four and requires one sale to
retain the incumbent one-slot reserve.

This is the active-row physical-fill residual explicitly excluded from closed PR
#11840. Engine-inactive suffix rows remain predecessor-owned, so this packet does
not silently absorb the separate market-prefix factor.

## One-factor candidate

`physical_fill.py` replaces only `SellScheduler.receipt_profile()` in a verified
copy of the canonical runtime. The replacement:

1. clips only valid `BUY_PRODUCT` / `BUY_ANIMAL` rows inside the official
   `max(1, maxMarketOrdersPerTurn)` prefix;
2. respects row order, so a same-turn target SELL frees capacity only when it
   actually precedes the purchase;
3. preserves oversized unit-stage arrivals and the existing one-slot reserve;
4. preserves inactive suffix behavior; and
5. fails closed to the unchanged predecessor when a later represented PICKUP or
   SELL could consume the clipped item and require a fuller item-flow model.

Affordability remains a conservative upper bound: insufficient cash can reduce a
purchase further, never increase it. No price, rival, target, ranking, horizon,
funding, action-materialization, configuration, archive, pointer, provider,
Kaggle, or submission policy changes.

## Executable custody and causal evidence

`materialize.py` verifies the exact current archive, `CURRENT-ARCHIVE.json`,
`CURRENT-SOURCE.json`, archive `SOURCE.json`, safe tar membership, and every
runtime byte/hash record. It creates independent control and candidate arenas
outside the checkout and proves that only `scheduler.py` differs.

`audit.py` binds the scheduler, frozen-selected consumer, official engine,
archive pointer, source manifest, evaluator, patch range, workflow, panel
orchestrator, comparator, and all candidate files. `trace_evaluator.py`
fail-closed patches the exact repository evaluator to retain a digest of only the
tested arm's returned actions.

`run_panel.sh` executes control and candidate against public Arlene and frozen V1
over eight independent environment seeds and both seats: 32 cells per arm, 64
complete official-interpreter games. `compare.py` rejects source, evaluator,
opponent, seed, lifecycle, cell, or action-causality drift and clusters evidence
by environment seed rather than treating mirrored seats as independent.

A valid unfavorable result remains a successful experiment. `ADVANCE` requires
no negative own-cash activation, no new loss or lost win, nonnegative opponent ×
seat strata, positive global own-cash effect, and at least six positive / zero
negative independent seed clusters with an exact one-sided sign tail at most
0.05. Other terminal verdicts are `INACTIVE`, `REJECT`, or `MORE_EVIDENCE`.

## Predecessor-killing contracts

The focused suite covers animal and product fills, capacity clipping, exact
source drift, same-turn sale-before-purchase and purchase-before-sale ordering,
engine-inactive suffix preservation, downstream PICKUP fallback, oversized
unit-stage overflow preservation, official-engine execution, materialization
closure, evaluator trace binding, comparator cell counting, and closed-loop
causality.

## Bound identities

- construction base: `4a26ad897efe3fc3349c6126e2747e49ca9f5ead`
- canonical archive SHA-256: `5f6a4153e502713b9467776eafe7464af650584149173ce7507a31a1b2af60f1`
- canonical scheduler Git blob: `a483b24dd72b580d7d8811636b54d2d44f391575`
- frozen-selected Git blob: `fc7baf5c179818a55037f6a61d92984d81d1a21c`
- official engine Git blob: `3c202c7ee921da239356789e266b694635103fc4`
- archive pointer Git blob: `5bd67f93b832b6f35ea6482d35cebdd0d600cbe1`
- source manifest Git blob: `d80b40e345bcdbacfed9f7f4c8173aeb134fd781`
- evaluator Git blob: `077feb2208b6e0c1727835eb4f8089709bf67f3b`

Canonical runtime/config/archive/pointers and Kaggle state are unchanged.
