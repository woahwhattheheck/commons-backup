# R04-EXPANDTAX — BUY_LAND weed-tax gate

Default-OFF (`r04_expandtax`, literal `true` only). OFF callers retain exact action identity.

## Mechanic (pinned official engine)

`_do_buy_land` converts every `"LOCKED"` tile of the purchased quadrant to `None`
(`LAND_ORDER = ["NE","SW","SE"]`, prices `[1000,2000,4000]`). `_spawn_weeds` rolls
`rng.random() < weed_chance` (default 0.005) for every `None` tile at EOD. Locked
tiles are therefore exempt; expansion adds roughly 25 tiles of potential weed
surface plus its unlock cash cost.

Gemini/Antigravity's expansion-penalty request asked for this quantification.
Canonical opening-expansion research established that exposure scales with empty
unlocked tiles. This package is the source-only gate; it is not a second scheduler.

## Gate rule

Expand iff `E > W·A + C/(T·D)`:

- `E` — trailing net dollars per planted tile per day
- `W` — measured weed-tax actions per new tile per day (`0.013`)
- `A` — trailing net dollars per non-PASS action
- `C` — price of the next canonical quadrant
- `T` — 25 tiles per quadrant
- `D` — remaining episode days

## Engine-bound admission

`filter_market_orders(action, observation, configuration, books)` is conservative:

- only the official executable market prefix (`max(1, maxMarketOrdersPerTurn)`,
  default 10) may change; the inert suffix is preserved exactly;
- one pre-callback verdict can admit at most the first executable `BUY_LAND`;
  later same-callback land rows are removed because their $2k/$4k post-commit
  state is not authenticated by the pre-callback evidence;
- canonical unlocked-quadrant order must be exactly a prefix of `NW,NE,SW,SE`;
- `day`/`step`, market cap, and trailing books use strict non-coercing evidence;
  bool/string/nonfinite/type-poison cannot mint a positive expansion verdict;
- malformed positive-evidence custody blocks executable `BUY_LAND` rather than
  fabricating a price/horizon. Malformed action/cap surfaces fall back to identity.

The helper does not claim that a retained `BUY_LAND` will execute; affordability
and any preceding market cash effects remain official-engine execution authority.

## Evidence

- `MEASUREMENT.md` — W = 0.0130 actions/tile/day from the pinned-engine spawn and
  clearing-cost panels.
- `GATE-VERDICT.md` — predecessor 16-cell frozen panel: dM(gate − always-expand)
  **+$938** mean (se $290, 9+/0−/7=) and dM(gate − never-expand) −$2,928.
  It remains micro-edge evidence, not activation authority; current tree-v4base
  re-gating is required before runtime promotion.
- `checks/test_expandtax.py` — 27/27 PASS normal, 27/27 PASS under `python -O`,
  plus `py_compile` on the hardened source/test bytes.

## Hook (only after a future activation gate)

See `WIRING.md`. The carrier ships the decision function only. The composer owns
live `TrailingBooks` custody and any runtime/config wiring.
