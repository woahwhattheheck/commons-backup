# POLAR seed liquidation economics

Research only, in the single V4 workspace on `main`. No result here authorizes a
PLANT/BUY_SEED change, feature activation, or submission.

## Engine-price calculator: use this for standard-market scenarios

`seed_shadow_value.py` is the original completed POLAR donor from
[issue #12645, comment 5642634973](https://github.com/woahwhattheheck/commons/issues/12645#issuecomment-5642634973).
It and `test_seed_shadow_value.py` are restored byte-for-byte in this existing
directory. The calculator models the pinned standard crop curves, integer quote
rounding, and sequential per-unit SELL commits. Sales at $1 pay cash but do not
increment public inventory. Already-committed output sells before the extra
specified output; an owned seed has zero avoidable purchase cost.

Reference commit: `465f4263da1c98acf78889d67cdd21b61dbba145`.
Engine blob: `3c202c7ee921da239356789e266b694635103fc4`.
These are historical source pins, not the current V4 integration head.

Run from this directory:

```sh
python -m py_compile seed_shadow_value.py test_seed_shadow_value.py
python -m unittest -v test_seed_shadow_value
python -O -m unittest -v test_seed_shadow_value
python seed_shadow_value.py --crop STRAWBERRY --inventory 10049 --yield-units 4
```

The recovery reran **20/20 tests normally and 20/20 under `python -O`**.
Each run includes 9,090 quote comparisons, 510 unit-liquidation comparisons,
and 425 baseline/combined/marginal comparisons. The default oracle executes
literal extracted official pricing/SELL definitions embedded in the donor test.
This is not a full engine, materialized agent, or episode run. Exact donor
identities, execution logs, and computed scenarios are in `RECOVERY-RECEIPT.json`.

An additional supported mode reads and authenticates the complete engine file
before extracting its actual definitions. It was **not** run for this recovery:

```sh
TITAN_ENGINE_FILE=/absolute/path/to/reference/engine/kaggriculture.py \
  python -O -m unittest -v test_seed_shadow_value
```

## Decision-relevant counterexamples, not forecasts

At STRAWBERRY inventory 10049, four units have a current quote of $26. Quote times
yield less a fresh $100 seed suggests +$4; actual isolated sequential revenue is
26 + 24 + 22 + 20 = $92, hence **-$8**. The same realized output from an already-owned
seed contributes **+$92**, before other avoidable costs; its sunk purchase price
must not justify skipping PLANT.

At inventory 10000 with 50 units already committed, the next four units contribute
only $84, making a new $100 seed **-$16**, despite current quote times four being
$480. Public inventory 10061 with five STRAWBERRY units yields $7 and ends at
inventory 10062 because the last four $1 sales do not increase stock.

All examples hold realized output and sale ordering fixed. They do not predict
watering, crop yield, town consumption, shop unlocks, opponent lockstep trades,
liquidation timing, feed utility, cash availability, or labor/cargo/route costs.
The bounded stock breakpoints are scenario diagnostics, not planting thresholds.
Paired complete-episode evidence remains necessary before policy changes.

## Preserved illustrative model: not engine-accurate

`polar_seed_liquidation.py`, `test_polar_seed_liquidation.py`, and `scenarios.json`
from #12647 remain unchanged for compatibility. They demonstrate sequential
liquidation with a synthetic **linear** `MarketBook`, including a configurable
zero floor. Merely embedding the engine's SHA does not make that model implement
the engine. Do not use those illustrative scenarios as official game economics.
Use `seed_shadow_value.py` above for the supported standard-market scenarios.
The unchanged seven-test illustrative suite was not rerun for this recovery.
