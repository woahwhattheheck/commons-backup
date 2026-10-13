# LANDSTAGE — locked-quadrant pre-positioning

Research-only HOMESTEAD sublane. No runtime, config, default, archive, workflow, or Kaggle activation is implied.

## Source-bound theorem

`land_staging_oracle.py` fails closed unless the official engine Git blob is `3c202c7ee921da239356789e266b694635103fc4` and the intact Arlene route bank Git blob is `bdb9cf58148a3c7961c085f4902759537decabf6`.

On those exact bytes it proves four mechanics directly from extracted engine functions:

1. Unit actions execute before `_process_market` in each callback.
2. In-bounds movement onto `LOCKED` tiles succeeds.
3. `BUY_LAND` unlocks NE, then SW, then SE by changing that quadrant's `LOCKED` tiles to `None`.
4. `_spawn_hand` ignores land ownership. From the default center position, the first three zero-occupancy hand spawns are `(5,4)` in NE, `(4,5)` in SW, and `(5,5)` in SE.

Therefore a farmer/hand may legally be inside the next still-locked quadrant before its `BUY_LAND` order commits. A hand hired in an earlier market slot of the same non-EOD callback may also already spawn in that future quadrant by the time the later `BUY_LAND` commits. It cannot unit-act until the next callback because the unit phase has already finished.

## Critical-path bound

From the default spawn `(4,4)`, the nearest future-quadrant tile is one move away for NE and SW and two moves away for SE. Without prior staging, a target-tile operation therefore needs at least 2 callbacks after the purchase for NE/SW and 3 for SE: move(s), then the tile operation. If a worker is already staged and survives the callback, the target-tile operation can occur on the next callback. The best-case post-purchase critical path can thus shift earlier by 1 callback for NE/SW and 2 for SE.

This does **not** make travel free. The movement must occur before purchase, so the mechanism is useful only when those earlier unit slots are cheaper than the post-purchase critical path.

## EOD guard

Market executes before end-of-day reset. A worker can technically be staged when a `BUY_LAND` order commits on the last callback of a day, but `_end_of_day` immediately resets the main farmer to the default shed-access tile and deletes all hands. The census therefore reports such a worker as staged-at-commit but **not** surviving to the next callback.

## Route census boundary

The oracle decodes the exact intact Arlene route bank and structurally simulates authored movement, HIRE, BUY_LAND, hand-spawn geometry, and daily worker reset. It reports every authored BUY_LAND event, worker positions at commit, pre-staged workers, same-callback prior hires, and whether staging survives EOD.

The route census is intentionally not an execution receipt. It assumes an authored HIRE/BUY_LAND row is reached and succeeds; it does not infer cash feasibility, market fills, runtime route selection, opponent behavior, or economic value.

From the `cloud-execution-lab` root:

```bash
python -B candidates/v4/research/opening-expansion-economics/land_staging_oracle.py . --output /tmp/land-staging.json
python -B candidates/v4/research/opening-expansion-economics/test_land_staging_oracle.py
python -O -B candidates/v4/research/opening-expansion-economics/test_land_staging_oracle.py
```

A current-tree execution receipt should preserve the emitted source identities and report the JSON SHA256 before any policy or native-integration discussion.
