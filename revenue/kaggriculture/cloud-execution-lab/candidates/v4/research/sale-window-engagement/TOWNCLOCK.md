# TOWNCLOCK — current-source E7 attribution successor

Status: **source-bound research/admission primitive; current-native economics not measured**.

This packet recovers the useful part of abandoned V3.1 PR #12423 into the
existing V4 `sale-window-engagement` authority. It does **not** revive the V3
router, create a seller, add a feature key, or claim that delayed selling wins.

## Current engine fact

Pinned official engine Git blob:

`3c202c7ee921da239356789e266b694635103fc4`

The interpreter processes market orders before `_town_consume`. On
`step % townCenterSellInterval == 0` (default 24), town-center consumption then
subtracts one unit of every town-center product except `FERTILIZER` and refreshes
prices. A SELL executed on that same step therefore receives the **pre-center**
quote; the deterministic -1 sink affects a later market opportunity.

This is only a timing opportunity. Rival supply is hidden/adaptive and can erase
or reverse the advantage. No domination or EV theorem follows.

## Donor-faithful question

Historical E7 did not ban authored/current SELL rows. It prevented the old
reservation layer from **advancing a future non-FERT sale onto the current
center tick**.

`townclock_attribution.py` preserves exactly that boundary. Given the current
optimizer's `(reference, plan)` timing tuples, it:

1. authenticates timing rows and requires equal total quantity;
2. preserves all current/due/base quantity already present in `reference`;
3. measures only units moved from future reference dates into `now`;
4. returns `VETO` only when `now` is a configured town-center tick and the
   product is not `FERTILIZER`;
5. returns `REFUSE` on malformed timing/configuration so an integration must keep
   its incumbent plan rather than guessing.

Future-to-future retiming is not E7. Extra quantity is not E7 and is refused
rather than laundered into a timing claim.

## Relationship to landed V4 timing work

- **HARVESTCLOCK** remains the fixed-tape full-interpreter timing oracle. Positive
  open-loop retiming value is opportunity mass, not adaptive policy proof.
- **H3S420** remains the current-source horizon/late-new-plan bridge. TOWNCLOCK
  does not alter its composer or native wiring.
- **DEMAND-CURVE** owns realized-shop / future-shop demand forecasting.
- The sole LOOM/native composer owns any executable one-stack integration.

This packet intentionally does not add another `FrozenSelected` rewrite while
that composition lane is live. The handoff is one admission call immediately
after a candidate `(reference, plan)` is produced and before it enters the
single/joint `options` set. `VETO` or `REFUSE` keeps the incumbent timing;
`PASS` leaves the existing selector unchanged. The same check must cover naive
or alternate selectors before claiming full semantic parity.

## Validation

Authored tests cover center/non-center ticks, FERT exclusion, configurable
intervals, due/base preservation, future-to-future retiming, duplicate-date
aggregation, quantity drift, malformed/past rows, fail-closed admission, engine
pin rejection, and deterministic census aggregation.

Run from this directory:

```sh
python -m unittest -v test_townclock_attribution
python -O -m unittest -v test_townclock_attribution
python -m py_compile townclock_attribution.py test_townclock_attribution.py
```

The CLI can census optimizer captures once the current native executor records
`now`, `item`, `reference`, `plan`, and `config`:

```sh
python townclock_attribution.py records.json \
  --engine /path/to/reference/engine/kaggriculture.py \
  --output TOWNCLOCK-CENSUS.json
```

A zero-VETO current-native census is **COLD**, not evidence that the engine fact
is false. A nonzero census is only engagement; both-seat adaptive economics is
still required before any activation language.
