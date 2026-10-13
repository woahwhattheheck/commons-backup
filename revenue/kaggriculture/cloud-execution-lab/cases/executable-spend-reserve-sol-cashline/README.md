# TITAN V3 executable spend-reserve closure (SOL-CASHLINE)

## Finding

The frozen SELL scheduler's `cash_reserve()` walks every authored market row. The pinned interpreter first converts a list-valued market queue and truncates it to `q[:max(1, maxMarketOrdersPerTurn)]`; capped suffix rows are never parsed or executed.

That mismatch is score-facing when exposed. A baseline SELL in the active prefix followed by a suffix `HIRE` or `BUY_LAND` can create a fictitious reserve deficit. `SellScheduler.act()` then maps `farm['money'] < budget` to `minimum=current[item]`, preventing the optimizer from reducing an immediate sale even though the alleged purchase cannot execute. Capped HIRE and land rows also advance the scheduler's projected Fibonacci/land cursors and inflate later reserve estimates.

## Repair

The in-memory carrier in `repair.py` binds:

- main commit `2e2e7e52fd2d5c62117ac49c7f1eabb505078ffb`;
- scheduler Git blob `a483b24dd72b580d7d8811636b54d2d44f391575`;
- pinned engine Git blob `3c202c7ee921da239356789e266b694635103fc4`;
- the engine's exact raw-prefix anchors; and
- the exact `cash_reserve -> budget -> minimum_now` source anchor.

It changes one hunk: derive the engine's effective minimum-one cap once, accept only list-valued queues, and quote only the active raw prefix. The patch does not change order parsing, costs, optimizer ranking, receipt/capacity projection, pending targets, emission, controller routes, configuration defaults, or any canonical package/archive pointer.

## Frozen-route exposure atlas

Semantic correctness does not prove present-score exposure. `route_exposure.py` therefore authenticates frozen Arlene Git blob `bdb9cf58148a3c7961c085f4902759537decabf6`, decodes the production `Agent.R` graph, and reports cap-by-cap structural activation for every named route.

The atlas records:

- route cells and deduplicated conserved cells whose market tape exceeds each cap;
- suffix spend rows by `HIRE`, `BUY_LAND`, `BUY_SEED`, `BUY_ANIMAL`, and `BUY_PRODUCT`;
- cells with an active-prefix SELL plus suffix spend, the direct false-deficit shape;
- representative route/step witnesses; and
- whether the defect is `EXPOSED` or `DORMANT_AT_DEFAULT_CAP`.

Shared prefixes are deduplicated by `(step, canonical market payload)` so aliases do not manufacture support. The source-bound Arlene output cap distinguishes current `Agent.act()` output from future raw-route reads. The receipt always sets `scoreboard_causality_claim=false`; matched official-interpreter evidence remains mandatory before strength or promotion claims.

## Evidence contract

`test_repair.py` executes 14 deterministic contracts, including:

- capped HIRE, land, seed, animal, and product purchases;
- `maxMarketOrdersPerTurn <= 0` mapping to one;
- HIRE Fibonacci and land-cursor non-advancement through inactive suffix rows;
- current and future route rows;
- exact predecessor identity when every row is active;
- non-list queues matching the interpreter's empty-queue behavior;
- malformed-cap failure; and
- a direct false-deficit witness where predecessor `(budget, minimum_now)=(1000,10)` becomes `(0,0)`.

`test_route_exposure.py` adds five contracts for exact Arlene binding, deterministic JSON, complete monotone cap series, alias-safe counts, and honest non-causality classification.

Run:

```bash
python revenue/kaggriculture/cloud-execution-lab/cases/executable-spend-reserve-sol-cashline/test_repair.py
python revenue/kaggriculture/cloud-execution-lab/cases/executable-spend-reserve-sol-cashline/test_route_exposure.py
python revenue/kaggriculture/cloud-execution-lab/cases/executable-spend-reserve-sol-cashline/repair.py --repo . --format json
python revenue/kaggriculture/cloud-execution-lab/cases/executable-spend-reserve-sol-cashline/repair.py --repo . --format patch
python revenue/kaggriculture/cloud-execution-lab/cases/executable-spend-reserve-sol-cashline/route_exposure.py --repo .
```

## Disposition boundary

This is an additive exact-source repair/evidence carrier. It makes no matched-game, W/T/L, leaderboard, V3 promotion, or Kaggle claim. It does not own the active cashflow-atlas, `receipt_profile`, E20/committed-HIRE, market-compaction, rival-supply, L01 tranche, one-tree publication, canonical archive, provider, or submission lanes. Composition requires current-base rebinding, all-off identity, returned-action activation, and a paired both-seat panel under the existing strict own-cash/margin/outcome gates.
