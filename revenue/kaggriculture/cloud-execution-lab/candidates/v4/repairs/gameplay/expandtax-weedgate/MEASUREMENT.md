# R04-EXPANDTAX — weed-tax measurement (pinned official engine, 2026-09-12)

Authority: `~/workspace/build/v4/redteam-official/official/kaggriculture.py`.

## 1. Spawn rate on newly unlocked tiles

Harness: `measure_weed_tax.py --mode tax` (fixed in this session: the interpreter
reads the step counter from the observation, which the harness must maintain or
EOD/`_spawn_weeds` never fires).

- Arms: `one` (NW only) vs `four` (NE+SW+SE bought at step 0), 100 seeds × 30 days,
  carrot-monoculture BFS sweeper, identical otherwise.
- `weeds_spawned` counts EOD `_spawn_weeds` events on previously-None tiles.
- Delta per new tile per day: (four − one) / (75 new tiles × 30 days).

Result: **0.00460 spawns/tile/day** (stdev 0.00151, n=100). Engine theory 0.00500;
the measured shortfall is honest — some unlocked tiles get planted/occupied,
shrinking the eligible None set.

Raw: `/tmp/tax.jsonl` (200 rows).

## 2. Clearing cost per spawned weed

Harness: `measure_weed_cost.py` — 10 weeds scattered across random empty tiles
(placement RNG seeded per episode), single farmer on weed duty, count DIGs +
weed-chase moves until cleared, 30 seeds.

Result: **2.83 actions/weed** (stdev 0.41, 30/30 cleared).

## 3. Weed-tax constant

```
W = 0.00460 × 2.83 = 0.0130 actions per new tile per day
```

`WEED_TAX_ACTIONS_PER_TILE_DAY = 0.013` in `expandtax.py`. Interpretation: each
newly unlocked tile costs ~0.013 farmer-actions/day in expected weed clearing,
priced at the agent's trailing $/action in the gate rule.
