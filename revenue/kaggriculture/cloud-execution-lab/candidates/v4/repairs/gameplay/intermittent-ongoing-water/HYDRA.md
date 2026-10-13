# HYDRA — intermittent ongoing-crop watering

Status: **SOURCE_BOUND / DEFAULT_OFF / NATIVE ECONOMICS NOT ASSESSED**.

This package belongs to the sole canonical `candidates/v4` tree. It is not a new controller, keyspace, runtime, or composition authority.

## Pinned mechanism

Authority is `reference/engine/kaggriculture.py` Git blob `3c202c7ee921da239356789e266b694635103fc4`.

The official engine establishes four relevant facts:

1. A newly planted crop begins with `consecutive_unwatered = 1`; if it reaches EOD without WATER it increments to 2 and becomes a WEED. Planting-day WATER is therefore mandatory.
2. WATER sets `watered_today = True`; at EOD this resets `consecutive_unwatered` to 0. An established plant at streak 0 can miss exactly one EOD and survive at streak 1.
3. TOMATO/STRAWBERRY base ongoing production is evaluated after the survival check and does not require `was_watered` once the plant survives.
4. Fertilizer bonus *does* require `was_watered`. HYDRA therefore refuses to suppress WATER on a production EOD when an active fertilizer bonus can increase unclipped yield.

The source helper rewrites only a selected `WATER` row to `PASS`. It does not add movement, PLANT, market orders, or a new schedule. It fails closed on nonstandard configuration, planting day, prior missed-water streak, malformed state, non-ongoing crops, already-watered tiles, duplicate same-site WATER rows, and same-turn PLANT→WATER constructions not visible as an established plant.

## Local source preflight

The exact authored helper/tests passed:

```text
python -m unittest -v test_ongoing_water_skip.py   # 15/15 core tests in isolated preflight
python -O -m unittest -v test_ongoing_water_skip.py # 15/15 core tests in isolated preflight
python -m py_compile ongoing_water_skip.py test_ongoing_water_skip.py
```

The repository checkout adds one engine-identity test, so the in-repo suite is 16 tests and must authenticate the pinned Git blob before this source can be treated as source-bound.

## Native handoff — existing assembler only

Do **not** create another V4 or watering controller. The existing native assembler should bind this helper at the final selected unit-action surface, after the selected action is known but before returned-action receipts are committed.

For OFF/ON current-native census, record at minimum:

- exact runtime/source identities;
- callbacks and fallback/deadline counts;
- authored WATER rows by crop;
- `plan_ongoing_water_skip` eligible rows by crop/day/hour;
- rewrite count and follow-up next-day WATER count for each rewritten tile;
- any plant loss/WEED transition after a rewrite (must be zero);
- fertilizer-bonus blocks and prior-streak blocks;
- terminal own/rival cash and margin, both seats.

A zero-engagement panel is **COLD**, not a mechanism kill. Positive engagement is not promotion: both-seat official-engine economics still belong to the current native integration/gauntlet owners. HARVESTWINDOW retains rot/deadline ownership, PHENOLOGY retains traversal/performance, and GHOSTPLANT retains atomic PLANT admission.
