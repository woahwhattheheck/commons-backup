# E3 strict price-forecaster donor

Purpose: preserve the useful E3 forward-price idea while quarantining the stale
donor's action-rewrite hazards until the final V3.1 stack exists.

## Provenance

- source branch before this donor: `riot/v3.1-lane-e3`
- source head: `2baa5b8c596e803f25f2a26f3e697a88fd12c007`
- original `overlay/r04_price_forecaster.py` blob:
  `b7b00c0ca987f417b7ca826c76c8e55591d8016b`
- original focused test blob:
  `3358e11d56cf25ecdbaf0edf67fea3371aba7752`
- the feature remains default OFF.

The original donor is intentionally left byte-identical for provenance. The
files in this directory are the hardened successor contract to consume later.

## Defects closed by `strict_price_forecaster.py`

The original `_apply()` scans every SELL row, deletes fully deferred rows and
then compacts the market list. It also accepts several runtime values through
`int()` / `float()` coercion. That is unsafe for final-stack composition:
late SELL rows can cross an earlier operation/barrier, row indices can shift,
and bool/string/float poison can silently become decision evidence.

The strict donor instead:

1. inspects and rewrites only the exact leading contiguous SELL block;
2. treats the first falsey or non-SELL row as a hard barrier;
3. preserves market-list cardinality and every tail index;
4. represents a fully deferred leading SELL as `[]` rather than deleting it;
5. requires strict non-bool types for step, player, quantity, inventory,
   prices, cash, shops, relevant tape orders and rival-flow state;
6. fails the whole rewrite closed to the original action on ambiguous input;
7. snapshots and restores E3 flow/telemetry if a forecast helper fails.

`test_strict_price_forecaster.py` is a focused regression contract covering
the barrier/cardinality theorem, partial rewrites, coercion poisons, poisoned
rival state, and state rollback.

## Consumption contract

This is a **source donor only**. It does not change the router, `apply_v3.py`,
`FILES.json`, manifest, defaults, package bytes, evaluator, provider or Kaggle.

A future current-stack E3 consumer must either:

- port this strict boundary into the final `r04_price_forecaster.py`; or
- wire this wrapper in place of the stale `_apply()` implementation,

then regenerate package custody on the literal then-current V3.1 base and run
opponent-diverse paired economics. Do not flip `r04_price_forecaster` ON from
this donor alone.
