# V5 RNG shop robustness research

This component turns the current pinned engine's shop-unlock RNG coupling into an exact, auditable research primitive. It does **not** activate a gameplay policy and it does not modify the frozen V4 package, runtime, defaults, config, archive, or Kaggle artifact.

## Source contract

Pinned engine Git blob: `3c202c7ee921da239356789e266b694635103fc4` (`reference/engine/kaggriculture.py`). At end of day it constructs:

`random.Random((seed * 1_000_003) ^ day)`

Then, for every farm, `_spawn_weeds` performs exactly one `rng.random()` for every tile whose value is `None`. Plant and animal daily refreshes contain no RNG calls. After all farms are scanned, an eligible shop unlock uses `rng.choice(sorted(SHOPS))`. Therefore the shop cursor depends on the **total number of None tiles across all farms**, not on which seat contributed each draw.

The default unlock interval is 3 days, unlocks are with replacement, and the total shop-instance cap is 8.

## What the solver certifies

`rng_shop_robustness.py` provides:

- `shop_unlock_due`: the exact unlock cadence/cap predicate;
- `shop_draw`: exact pinned-source shop prediction from seed/day and per-player empty counts;
- `stable_shop_intervals`: maximal total-empty-count windows that map to the same exact shop;
- `robust_options`: evaluates each caller-supplied reachable own count against **every** caller-supplied rival count. It reports an exact shop only if every rival count agrees, and target-set robustness only if every outcome lies in the target set.

No probability is inferred from an uncertainty set. Legal reachability is intentionally external: this tool will not pretend that an arbitrary empty-count delta is executable by the policy.

## Fresh-loss-seed result

The two exact public-loss rematch seeds recorded on V5 main reveal nontrivial stable cursor windows:

- Sian loss seed `2051966578`, end-of-day `5` (unlocking day 6): total `None` count `42..47` yields `BRUNCH_SPOT` for all six cursor positions.
- Sian loss seed `2051966578`, end-of-day `11` (unlocking day 12): total `None` count `33..37` yields `BAKERY` for all five positions.
- Gracie loss seed `1378040481`, end-of-day `14` (unlocking day 15): total `None` count `42..46` yields `BAKERY` for all five positions.

Constructed robustness witness: on the first cell, own count `22` plus rival uncertainty `20..25` produces total counts `42..47`, so the result is exactly `BRUNCH_SPOT` across all six rival states. This proves the robustness theorem is not vacuous. It is **not** a claim that those empty counts occurred in the historical loss or are reachable by a one-turn live action; a state/reachability owner must certify that separately before any policy experiment.

## Run

From this directory:

```text
python -B test_rng_shop_robustness.py
python -O -B test_rng_shop_robustness.py
```

A source-identity test computes the Git-blob SHA of the pinned engine and fails closed if engine semantics drift.
