# TITAN V4 land-expansion weed pressure

Source-bound research for the random-weed cost of unlocking empty land. This is
an **evidence surface, not a BUY_LAND policy**. It quantifies the maintenance
hurdle created by additional `None` tiles under the pinned official engine and
keeps production value, routing value, and current-V4 economics as separate
admission gates.

## Pinned authority

The oracle authenticates the exact checked reference before importing or
reading defaults:

- reference artifact: `10175943272`;
- archive SHA-256:
  `b567942e4fb4e0571ebf9f8eaaf143d4a9156df3289f09a98db37823ef4d68d9`;
- `engine/kaggriculture.py` Git blob:
  `3c202c7ee921da239356789e266b694635103fc4`;
- engine SHA-256:
  `bc8a54879ef02c7ea64b8b333d6a976f0ea65c4949149d01f463f23bccee653e`;
- `engine/kaggriculture.json` Git blob:
  `b354d06b742fe48402513792253f1a5c29366b20`;
- config SHA-256:
  `a82c89c1a2315b93f39775d8e025471a01b738647c9772658368ee6b1b6f4867`.

Pinned defaults are board size 10 and random weed probability 0.005 per eligible
empty tile per end-of-day refresh. Land prices are $1,000, $2,000, and $4,000,
so moving from the initial quadrant to all four costs $7,000 and unlocks 75
additional tiles.

## Mechanism boundary

`_spawn_weeds` rolls only when a tile is literally `None`. `LOCKED` tiles,
plants, animals, structures, and existing weeds do not draw a random-spawn roll.
So an all-empty four-quadrant board is a **maximum empty-land exposure**, not the
weed burden of a productive four-quadrant farm. Productively occupying an extra
tile removes that tile from this random-spawn surface.

A random weed requires at least one `DIG` to clear. The perfect-clear panel
therefore gives a lower bound on maintenance actions; movement and routing are
additional. The persistent panel instead leaves weeds uncleared, measuring a
passive occupancy envelope rather than an action cost.

The official end-of-day RNG is shared across players. The deterministic 100-seed
rows here isolate the first farm's weed stream for a clean same-seed Q1/Q4
comparison. The analytic expectation (`eligible_tiles * 0.005 * days`) is
seat-independent, but this package is not a both-seat current-runtime receipt.

## 100-seed result, days 0-29

Seeds are exactly 1 through 100. With daily perfect clearing:

| Measure | Q1: 25 empty unlocked tiles | Q4: 100 empty unlocked tiles | Q4-Q1 |
| --- | ---: | ---: | ---: |
| analytic expected random weed events | 3.75 | 15.00 | 11.25 |
| observed mean | 3.79 | 15.14 | 11.35 |
| observed median | 3.5 | 15.0 | 11.5 |
| observed min / max | 0 / 9 | 5 / 24 | 3 / 21 |
| paired sign |  |  | 100 positive / 0 zero / 0 negative |
| paired 95% t interval |  |  | 10.6694 to 12.0306 |

With no clearing, final random-weed occupancy after 30 days is:

| Measure | Q1 | Q4 | Q4-Q1 |
| --- | ---: | ---: | ---: |
| analytic expected final weeds | 3.4904 | 13.9616 | 10.4712 |
| observed mean | 3.48 | 14.08 | 10.60 |
| observed median | 3 | 14 | 11 |
| paired sign |  |  | 100 positive / 0 zero / 0 negative |

Every exact seed row is in `SEED-RESULTS.csv`; machine-readable aggregates are
in `RESULTS.json`.

## Break-even contract

The random-weed component of a Q1 -> Q4 decision is small enough to state
exactly and narrow enough that it must not be confused with total land EV.

For 75 extra tiles kept empty and perfectly cleared for 30 days:

- upfront land cash: **$7,000**;
- expected extra random weeds / minimum DIGs: **11.25**;
- expected random DIG burden per extra empty tile: **0.15** over the season;
- average upfront cash per extra tile: **$93.33**.

If `A` is the opportunity value of one DIG action, the minimum hurdle represented
by this oracle is:

`$7,000 + 11.25*A + travel/routing opportunity cost`.

Expansion is economically justified only if the incremental production,
placement, congestion relief, and routing value of the extra land exceeds that
hurdle plus any other costs. Because productive occupancy removes random weed
exposure, the real weed term can be materially *below* 11.25.

Marginal land-price density also worsens by tranche: the first, second, and
third added quadrants cost $40, $80, and $160 per newly unlocked tile
respectively. A current-native policy should therefore evaluate each unlock
incrementally rather than treating “1 quadrant” and “4 quadrants” as the only
choices.

## What this does **not** prove

This package does not prove hyper-dense Q1 farming is strictly superior. It does
not value crop/animal output, future structures, worker congestion, path length,
market timing, current lane composition, or rival behavior. It also does not
change `BUY_LAND`, defaults, runtime source, the canonical archive, or Kaggle
state.

The correct downstream gate is a current-composed, both-seat native comparison
that binds each land purchase to realized occupancy/production value, actual
weed service actions and travel, cash timing, and fallbacks/deadlines. Use this
oracle as the random-weed term in that decision, not as the decision itself.

## Reproduce

```sh
export TITAN_ENGINE_PATH=/absolute/path/to/reference/engine/kaggriculture.py
export TITAN_CONFIG_PATH=/absolute/path/to/reference/engine/kaggriculture.json

python -B -m unittest -v test_expansion_penalty.py
python -O -B -m unittest -v test_expansion_penalty.py
python -m py_compile expansion_penalty.py test_expansion_penalty.py

python -B expansion_penalty.py \
  --engine "$TITAN_ENGINE_PATH" \
  --config "$TITAN_CONFIG_PATH" \
  --seed-start 1 --seed-count 100 --days 30 \
  --csv-out /tmp/expansion-seeds.csv \
  --json-out /tmp/expansion-results.json
```

Authored verification is 7/7 PASS under normal Python, 7/7 PASS under
`python -O`, zero skips, plus `py_compile` PASS. Source and result identities are
recorded in the pull-request receipt and can be recomputed byte-for-byte.
