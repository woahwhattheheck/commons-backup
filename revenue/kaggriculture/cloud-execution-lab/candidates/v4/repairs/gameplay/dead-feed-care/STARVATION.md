# TITAN V4 STARVEORACLE — intermittent feeding mechanism

This package is a source-bound **mechanism verifier**, not an activation policy.
It lives in the existing `repairs/gameplay/dead-feed-care/` family because the
new finding directly interacts with FEED/CARE service semantics.

## Pinned source

The verifier authenticates and executes the official Kaggriculture engine from
already-trusted reference artifact `10175943272` / checked archive
`b567942e4fb4e0571ebf9f8eaaf143d4a9156df3289f09a98db37823ef4d68d9`.

- `engine/kaggriculture.py` Git blob:
  `3c202c7ee921da239356789e266b694635103fc4`
- SHA-256:
  `bc8a54879ef02c7ea64b8b333d6a976f0ea65c4949149d01f463f23bccee653e`

`starvation_cadence.py` refuses any other engine bytes before execution.

## What the engine actually guarantees

At end of day, a fed animal resets `consecutive_unfed` to zero. An unfed animal
increments it by one; escape occurs only when the counter reaches two. A
surviving animal then enters production **whether or not it was fed that day**.
The base production increment is one on the species production cadence, and the
engine sets `fertilizer_available = True` for every surviving animal.

Therefore a cadence that never permits two consecutive unfed days can preserve
base production and fertilizer availability while reducing WHEAT feed.

The important exception is CARE. `pending_care_bonus` is consumed on a
production day only when `fed_today` is true, and the engine clears the pending
bonus after that production check. CARE is banked for the future only when the
animal was both cared for **and fed** that day. A blanket "feed every other day"
rule can therefore destroy valuable CARE output even though the animal survives.

## Complete-interpreter control

The authored verifier constructs one placed animal on the official initialized
board, then executes the exact official `interpreter()` for all 720 season steps.
The actor collects fertilizer daily and, in the uncapped control, harvests daily;
this isolates animal refresh semantics from held-output clipping. No gameplay
source is patched.

With CARE disabled, both alternating phases survive for every species and match
daily feeding exactly on base product and fertilizer output:

| Species | Daily WHEAT | Alternate WHEAT | Daily product | Alternate product | Fertilizer daily / alternate |
| --- | ---: | ---: | ---: | ---: | ---: |
| GOOSE | 30 | 15 | 27 EGG | 27 EGG | 30 / 30 |
| COW | 30 | 15 | 12 MILK | 12 MILK | 30 / 30 |
| SHEEP | 30 | 15 | 9 WOOL | 9 WOOL | 30 / 30 |

The same equality holds in the no-harvest held-cap control: GOOSE caps at 4,
COW at 6, SHEEP at 6 under both schedules. Two consecutive unfed days causes
escape on the second end-of-day refresh for all species.

The verifier's constructed protocol performs one PICKUP and one FEED on each
feed day, so those attempted actions fall from 30 to 15 as well. That is a
harness fact, not a claim that every production route saves two worker actions;
a live policy may already carry WHEAT.

## CARE counterexample — blanket activation is rejected

When the constructed actor CAREs every day, daily feed materially outproduces
the same alternating feed cadence even though alternating still halves WHEAT
and preserves fertilizer:

| Species | Daily-feed product | Alternate-feed product | Product lost |
| --- | ---: | ---: | ---: |
| GOOSE | 56 EGG | 27 EGG | 29 EGG |
| COW | 39 MILK | 12 MILK | 27 MILK |
| SHEEP | 38 WOOL | 13 WOOL | 25 WOOL |

These are **mechanism controls**, not field EV. Market prices, routing, current
natural CARE engagement, storage pressure, production timing, and opponent
behavior can change the economic choice. The correct follow-on is a
CARE-aware/native scheduler gate, not immediate global activation.

## Admission rule for downstream owners

A future current-runtime policy may consume STARVEORACLE only if it proves all
of the following for each skipped FEED:

1. the animal cannot reach two consecutive unfed days before the next effective
   feed;
2. the skipped day is not sacrificing a CARE bonus whose value dominates the
   saved WHEAT / service action;
3. held-output/storage constraints do not invalidate the claimed benefit;
4. the exact current composed V4 route can still execute the next feed in time;
5. both-seat native economics and fallback/deadline behavior are revalidated.

This package does not add a feature key, controller, default, archive mutation,
Kaggle submission, or promotion claim.

## Reproduce

Set `TITAN_ENGINE_PATH` to the exact pinned official engine file extracted from
the checked reference artifact:

```sh
export TITAN_ENGINE_PATH=/absolute/path/to/engine/kaggriculture.py
python -B -m unittest -v test_starvation_cadence.py
python -O -B -m unittest -v test_starvation_cadence.py
python -m py_compile starvation_cadence.py test_starvation_cadence.py
python -B starvation_cadence.py --engine "$TITAN_ENGINE_PATH" \
  --output /tmp/starvation-receipt.json
```

Exact authored source and test identities, execution counts, and compact control
rows are in `STARVATION-VALIDATION.json`.
