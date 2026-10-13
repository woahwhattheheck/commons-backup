# V4 scheduler executable-prefix repair

This directory preserves the current-main semantic port of the reviewed V3/V3.1 scheduler-prefix salvage from #12643.

## Why this exists

The official Kaggriculture interpreter normalizes each player's market vector to a list and executes only the raw prefix `q[:max(1, maxMarketOrdersPerTurn)]`. It does not compact falsey rows before slicing. The current scheduler still projects the entire authored market list in two places: `SellScheduler.cash_reserve()` and `SellScheduler.receipt_profile()`. A `HIRE` or `BUY_*` row beyond the executable raw prefix is therefore engine-inert but can still be charged/replayed by the scheduler's forecast.

The repair adds one shared `_engine_market_prefix()` helper and routes exactly those two projection consumers through it. It does not change the production scheduler in this commit; it is a source-order repair artifact for the canonical V4 composer/promotion gate.

## Provenance and drift custody

- Canonical integration line: `main`, per `candidates/v4/CANONICAL.json`.
- Reviewed donor materializer: Git blob `5e8f54ca20fa755bc6ced55decdcdf0193cda812` (durable #12643 receipt `5642641084`).
- Donor's old scheduler pin `da1b6fb571e79ba7dab54c8d816e45afb934e4d2` is stale and is **not** applied.
- Current-main scheduler pin used here: Git blob `a483b24dd72b580d7d8811636b54d2d44f391575` at `revenue/kaggriculture/cloud-execution-lab/scheduler.py`.
- Official engine pin: Git blob `3c202c7ee921da239356789e266b694635103fc4` at `revenue/kaggriculture/cloud-execution-lab/reference/engine/kaggriculture.py`.

`materialize_scheduler_prefix.py` refuses source/engine drift, exact-anchor ambiguity, double application, or in-place output aliasing. `test_scheduler_prefix_repair.py` binds the current source and engine bytes, compiles the postimage, proves both projection consumers are rewired exactly once, checks double-apply fail-closed behavior, and exercises the raw-prefix semantics including falsey slot preservation and the engine's nonpositive-cap clamp to one.

## Boundary

No V4 key/default is changed. No detached V3/V3.1/V4 ref is advanced. No legacy V4 materializer is executed. No production archive, provider, evaluator, Kaggle, or submission state is changed. Promotion of the generated scheduler postimage must occur only after re-reading the exact source/engine pins and running the focused regression plus the surrounding V4 gate against the then-current main line.
