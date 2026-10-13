# TOWNRNG — EOD weed-stream / public-shop coupling

Status: **source-confirmed causal-integrity oracle; not a gameplay policy**.

This is the single canonical V4 authority for the shared EOD weed-RNG -> public
shop mechanism inside `seat-asymmetry-audit`. PR #12892 established the paired
environment-divergence gate. PR #12858's temporary `research/rng-steering/`
package is converged here: its unique final-empty-tile counterfactual, per-seat
stream effect, shop-demand vector, and fixed 2,048-cell mechanism census are
preserved below and in `town_rng_coupling.py`; the duplicate root is removed by
the convergence carrier.

No controller, feature key, runtime patch, alternate V4, archive, default,
workflow, or Kaggle mutation is introduced.

## Exact source mechanism

Pinned official engine Git blob:

`3c202c7ee921da239356789e266b694635103fc4`

At end of day, the official interpreter creates one RNG:

`random.Random((seed * 1_000_003) ^ day)`

It then calls `_spawn_weeds` for farm 0, then farm 1, using that same RNG. The
weed scan calls `rng.random()` **only when the current tile is `None`**. After
both farm scans, the same RNG is used for `rng.choice(sorted(SHOPS))` when a
town-shop unlock is due.

Consequences:

- the shop RNG cursor advances by the **sum of both farms' pre-scan empty-tile
  counts**;
- redistributing the same total number of empty tiles between seats does not
  change the shop draw;
- changing total empty-tile count can change the next public shop at the same
  episode seed/day;
- `weedSpawnChance=0` removes weed placement, **not the RNG draws**. Every empty
  tile still evaluates `rng.random() < weed_chance`, so the coupling survives;
- because the shop is public and later consumes market inventory, a baseline and
  candidate can enter different public environment paths before later economic
  divergence is measured.

This is a paired-experiment confound and a state-level causal mechanism, not a
live exploit. No claim is made that a policy can infer or target the hidden
episode seed, reach a desired final-scan tile cheaply, or improve terminal
margin.

## Deterministic witnesses

On default shop cadence, `day=2` is an unlock EOD (`next_day=3`).

The original TOWNRNG witness uses episode seed 1:

- baseline pre-weed empties `[20, 20]` consume 40 RNG draws and select
  `SMOOTHIE_SHOP`;
- candidate empties `[20, 21]` consume 41 draws and select `BAKERY`;
- seat-swapping a fixed total `[13, 27] -> [27, 13]` leaves the shop unchanged;
- a counterfactual independent shop RNG leaves the shop unchanged across the
  40/41-empty pair, isolating shared-stream coupling.

The converged RNGSTEER witness makes the intervention direction explicit. With
episode seed 5, day 2, and `[25, 25]` currently-empty tiles:

- baseline public unlock is `PIZZA_SHOP`;
- occupying only seat 1's **final scan-order empty tile** yields `[25, 24]` and
  `BRUNCH_SPOT`;
- all farm-0 weed draws and all earlier seat-1 weed draws remain identical;
- the same shop flip still occurs with `weedSpawnChance=0`.

For seat 0, removing its final empty-tile draw preserves seat 0's earlier weed
draws but shifts the stream seen by seat 1 before the public shop. For the shop
itself, `[24,25]` and `[25,24]` are equivalent because only total draws matter.

## Fixed constructed census

`fixed_tail_fill_panel()` evaluates seeds 1..256 over default unlock EODs
`2,5,8,11,14,17,20,23`, with `[25,25]` as baseline and a seat-1 final-empty-tile
fill as the counterfactual:

- 2,048 cells;
- 1,336 public-shop flips;
- 712 unchanged shops;
- 65.234375% flip frequency in this constructed mechanism panel.

This is **not field EV or a natural activation rate**. It only quantifies how
often one removed RNG draw changes the public shop under this transparent state
model.

`shop_demand_vector()` exposes the resulting public-demand identity for
downstream evidence consumers. For example, the seed-5 witness changes the next
shop from `PIZZA_SHOP` demand `{MILK,TOMATO,WHEAT}` to `BRUNCH_SPOT` demand
`{EGG,WHEAT,STRAWBERRY}`. Single-product shops retain the engine's 2x quantity
rule.

## Gate rule for V4 economics

For any paired baseline/candidate run that can change empty-tile occupancy
(BUILD, DIG, PLANT, BUY_LAND, weed handling, land expansion, etc.), record
`town.unlocked_shops` at every EOD.

If the first shop list diverges, mark that cell
`ENVIRONMENT_PATH_DIVERGED` before attributing later market/margin changes to
the policy. Either:

1. report the downstream score separately as coupled-environment evidence, or
2. rerun the causal comparison with an explicitly controlled shop schedule /
   split-RNG experimental harness.

A changed empty count without an actual shop-choice divergence is exposure, not
proof of confounding on that cell. The RNG is re-seeded each EOD, so the gate is
day-local and should be checked at each unlock.

## Reproduce

From this directory:

```bash
python -B test_town_rng_coupling.py
python -O -B test_town_rng_coupling.py
python -m py_compile town_rng_coupling.py test_town_rng_coupling.py
python -B town_rng_coupling.py \
  --engine ../../../../reference/engine/kaggriculture.py \
  --output /tmp/TOWN-RNG.json
```

The CLI refuses engine-source drift before emitting a source claim.

## Boundaries

- `seat_symmetry_oracle.py` keeps its market-lockstep falsifier and direct
  weed-seat-stream witness.
- `TOWNRNG` owns the downstream shared-RNG -> public-shop causal boundary and
  the converged active occupancy counterfactual.
- seed-identifiability / hidden-seed inference remains a separate question.
- occupancy/weed/expansion policy economics remain with their existing owners.
- `research/rng-steering/` is superseded provenance from #12858 and must not be
  rebuilt as a sibling authority.

`promotion_decision = NOT_ASSESSED`.
