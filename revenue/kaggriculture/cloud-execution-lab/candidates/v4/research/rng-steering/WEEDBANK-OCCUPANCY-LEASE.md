# TITAN V4 — Gemini WEEDBANK as a reversible occupancy lease

This packet consumes the Gemini/Antigravity **WEEDBANK / zero-cost coop carpet** proposal inside the existing V4 RNG-steering research authority. It is research-only: no runtime key, controller, default, archive, evaluator, provider, Kaggle or submission path is added.

## Source verdict

Pinned official engine Git blob: `3c202c7ee921da239356789e266b694635103fc4`.

The useful mechanical core is real:

- `BUILD_COOP` converts an owned `None` tile into an empty `COOP` without cash cost.
- `DIG` removes plants, weeds and **empty** COOP/PASTURE tiles back to `None`; a placed animal is not removable this way.
- `_spawn_weeds` calls `rng.random()` only for `None` tiles.
- therefore an empty structure can temporarily suppress both weed risk and that tile's weed RNG draw, then be removed later.

The original framing is still too strong. "Zero cost" means zero **money**, not zero opportunity cost: BUILD consumes a unit action, restoring the tile consumes another DIG action, and the tile cannot be used for another purpose while leased.

## Critical policy split

Weed cleanup changes later RNG eligibility, so labor and RNG accounting must name the baseline policy. V2 refuses to produce a receipt without one of two explicit source-real baselines:

### A. `leave_first_weed_until_horizon`

The tile starts `None`. If a weed appears, it remains resident through the horizon and can be cleaned afterwards. The first weed therefore stops later weed draws.

For `N` EODs and weed chance `p`:

- probability / expected weed events = `1 - (1-p)^N`;
- expected eventual weed-cleanup actions = the same value, at most one;
- expected weed RNG draws = `(1-(1-p)^N)/p` for `p>0` (and `N` when `p=0`).

At `p=0.005`, `N=30`, this gives `0.13961580808530394` expected weed cleanup and `27.92316161706079` expected weed draws. Against a restored BUILD+DIG lease, direct action delta is `-1.860384191914696`.

### B. `clear_each_weed_before_next_eod`

Every spawned weed is DIGged before the next EOD; a terminal-horizon weed may be cleaned afterwards. That returns the tile to `None`, so it is eligible again and can reweed repeatedly.

For the same `N,p`:

- expected weed events / eventual cleanup actions = `N*p`;
- expected weed RNG draws = exactly `N`;
- against a restored BUILD+DIG lease, direct action delta = `N*p - 2`.

At `p=0.005`, `N=30`, this gives `0.15` expected cleanup actions, `30` expected weed draws and direct delta `-1.85`.

The difference is small at the standard weed chance but decisive at the boundary: with `p=1`, `N=3`, leave-first has one cleanup / one draw and direct delta `-1`, while clear-and-renew has three cleanups / three draws and direct delta `+1`. Therefore **there is no policy-independent sign theorem for direct weed labor**. Any result must carry the named baseline.

## What still survives: RNG steering

A structure consumes zero weed RNG draws while it occupies the tile. The number suppressed is baseline-policy dependent: truncated geometric under leave-first, exactly one per EOD under clear-and-renew. Existing TOWNRNG/RNGSTEER evidence shows that changing the weed-draw cursor can change later public shop RNG.

This packet deliberately gives that effect **no positive decision value**. Without an observable predictor and paired economic gate, a shop-path change is `ENVIRONMENT_PATH_DIVERGED`, not a policy win. SEEDIDENT's no-turn-1-omniscience boundary remains binding. V2 receipts explicitly set RNG decision, hidden-seed targeting, runtime policy, and global direct-labor-sign authority to false.

## Best-form V4 handoff

Do not ship a blanket carpet controller. A future field arm may test an occupancy lease only when all of these are separately proven by existing V4 authorities:

1. the exact baseline cleanup policy is declared and executable;
2. the structure has independent productive value **or** the experiment is explicitly testing RNG steering;
3. the tile is empty and remains animal-free;
4. BUILD reachability and any future restore-DIG reachability are executable;
5. temporary tile opportunity cost and BUILD/DIG action cost are charged;
6. every EOD records `town.unlocked_shops`, with first divergence tagged `ENVIRONMENT_PATH_DIVERGED`;
7. same-total-empty occupancy is retained as a negative control for mere geometry changes;
8. no hidden-seed reconstruction or clairvoyant shop targeting is claimed.

EXPANDTAX should consume this accounting too: BUY_LAND adds `None` tiles, which simultaneously changes weed exposure and the shared RNG cursor feeding later shop unlocks. Those effects must be reported separately from deterministic productive land value.

## Carrier

- `weedbank_occupancy_lease.py` — source-pin helper plus explicit two-policy labor/RNG accounting; emits no runtime authority.
- `test_weedbank_occupancy_lease.py` — engine-blob/anchor check, policy-separation killers (`p=1,N=3` and standard `p=.005`), zero-probability edges, type/policy poison and authority killers.

The v1 mixed-baseline statement is retired. Merge authority requires exact branch execution under normal Python and `python -O`, `py_compile`, and the pinned-engine path check.
