# Opening / Expansion Economics (ASTRA-HOMESTEAD)

Research-only evidence for the canonical TITAN V4 tree. This package consumes two
fresh hypotheses through one source-bound decision surface instead of creating
separate controllers.

## Authority

- official engine Git blob: `3c202c7ee921da239356789e266b694635103fc4`
- engine config Git blob: `b354d06b742fe48402513792253f1a5c29366b20`
- default board: 10x10, four 5x5 quadrants
- default weed spawn chance: `0.005` per eligible empty unlocked tile at EOD
- default day length: `24` callbacks
- starting money: `$3000`

`opening_expansion_economics.py` fails closed if either authority blob drifts.

## Expansion penalty result

The official `_spawn_weeds` kernel rolls only on `tile is None`. LOCKED tiles are
indeed exempt, but so are occupied crop/structure/weed tiles. Therefore weed
exposure scales with **currently empty unlocked tiles**, not with unlocked land
itself and not exponentially with quadrant count.

If every eligible site is cleared back to empty every day for 30 days:

- 25 empty tiles: exact expectation `25 * 30 * .005 = 3.75` weed spawns
- 100 empty tiles: exact expectation `100 * 30 * .005 = 15.0`
- raw all-empty expansion surcharge: `+11.25` expected weed-clearing events/season
- ratio: exactly `4x`, not exponential

Fixed seeds 1..100 through the source-equivalent Bernoulli kernel:

- 25 empty / clear daily: mean `3.68`, median `3.5`, range `1..10`
- 100 empty / clear daily: mean `14.46`, median `14`, range `7..27`
- 25 empty / never clear: mean `3.40`
- 100 empty / never clear: mean `13.44`

This is **not** a theorem that one quadrant dominates four. Productive occupation
shrinks the eligible set. A land purchase is penalized only to the extent the new
tiles remain empty (plus its cash/opportunity cost). The next policy-grade gate
must compare marginal production value vs cash + actual empty-tile weed labor.

## Zero-cost structure “action banking” result

`BUILD_COOP` / `BUILD_PASTURE` occupancy can suppress weed rolls on that tile, but
blanketing land does **not** bank a weed-clearing action for a later planting day.
A structure must be DIG'd before PLANT on every protected tile. For one otherwise
empty tile left untouched for 30 days, the probability it has ever weeded is only
`1 - .995^30 = 13.96%`; a prebuilt structure guarantees a future DIG on 100% of
tiles. Across 25 tiles that is 25 deterministic future DIGs versus ~3.49 expected
uncleared weeded tiles. Even if BUILD used otherwise-wasted idle time, the future
busy-day work is about 7.16x higher per protected tile. Treat blanket structures
as a narrow variance/occupancy tactic only, not default weed-action savings.

## “Goose Printer” result

The source facts behind the idea are real: GOOSE costs $300; animals set
`fertilizer_available=True` at EOD even before first product yield; market work is
processed after unit actions. But the stated no-hire Day-0 recipe omitted physical
custody and movement.

For `n` geese on distinct coops with one farmer, even an obstacle-free connected
path needs at least:

`n BUILD_COOP + n PLACE + (n-1) moves + 1 PICKUP = 3n unit actions`

The callback-0 BUILD can overlap the market BUY_ANIMAL order, but those purchased
geese enter the shed only after callback-0 unit work. For 10 geese:

- minimum unit actions: `30`
- Day-0 capacity: `24`
- after callback-0 build: `29` actions remain but only `23` callbacks remain
- verdict: **the literal 10-goose / one-farmer Day-0 opener is impossible**

The ideal lower-bound ceiling is 8 placed geese (`24` actions), hence at most 8
Day-0 fertilizer flags under that no-hire construction. This does not prove 8
geese is optimal. Hires can change feasibility and must be benchmarked as a
different opener, including hire cost, per-worker pickup/routes, feed/care burden,
market pressure, and foregone crop/land capital.

## Reproduce

From `cloud-execution-lab`:

```bash
python -B candidates/v4/research/opening-expansion-economics/test_opening_expansion_economics.py
python -O -B candidates/v4/research/opening-expansion-economics/test_opening_expansion_economics.py
python -B candidates/v4/research/opening-expansion-economics/opening_expansion_economics.py
```

No runtime, controller, config, default, archive, workflow, or Kaggle submission is changed.
