# GATE-DESIGN.md — why there is no engine gate, and what stands in for it

## The problem

The standard hardened gate (frozen 16-cell panel on the pinned engine)
*cannot* measure r04_shop_first: the pinned reference engine has no
shed→shop procurement mechanic (verified: `_town_consume` touches only
market inventory; `town_procurement.py` is buy-side only). On the pinned
engine the lane is provably inert — the `ShopLedger` never observes a tick,
so `filter_market_orders` returns every action unchanged. An engine gate
would report exactly $0.00 delta and prove nothing except the (already
unit-tested) inertness.

Fabricating an engine-gate number is explicitly out of scope. This note
documents the substitute instead.

## The substitute: replay-derived shop model (option a)

`shop_model.py` implements the live shop mechanic as measured from replays
and pits the lane's *actual* reserve filter (`_cap_sells_for_reserve`,
imported from the lane module — not a reimplementation) against the current
dump-everything behavior on our own replay-measured production schedule.

Assumptions (all replay-sourced, see module docstring A1–A8):
- tick every 24 steps (modal measured gap), 32u per-product per-tick cap
  (measured tick size), premium prices (measured), $100k demand cap
  (measured ~$92k, rounded up), our production inflow totals (measured),
  $0.60/u market realization (measured full-game average).

## Results

| Scenario | DELTA(ON−OFF) |
|----------|---------------|
| Base | **+$32,811** |
| Demand cap $50k | +$12,578 |
| Market realization $1.20 (2x) | +$32,464 |
| Tick cap 16u | +$28,961 |

Positive across all sensitivity runs. Calibration check: the model's ON
policy captures ~$70k in shop revenue — reproducing the observed
shop-farmer outcome (QQ Farming ~$73k). The model is not overfit to produce
a win; it reproduces the opponent's measured behavior.

## What this is and is not

- IS: a real measurement from a documented replay-derived model, using the
  lane's actual filter code, with sensitivity analysis. Sufficient evidence
  to file the carrier into the serial merge queue as default-OFF.
- IS NOT: a full-engine gate, a live A/B, or a promotion claim. Activation
  (flipping the default) requires a live-canary A/B on the leaderboard,
  never a pinned-engine argument.
- The pinned-engine no-regression property holds by construction (inert
  without observed ticks) and is covered by unit tests, not by games.

## Kill criteria (for the record)

Kill or rework this lane if: (1) live-canary A/B shows <= $0 at 95%
confidence; (2) shop demand proves already saturated by our current capture
(we already take ~$19k/game — the model says $70k is available, but live
competition for ticks may compress this); (3) the live mechanic changes.
