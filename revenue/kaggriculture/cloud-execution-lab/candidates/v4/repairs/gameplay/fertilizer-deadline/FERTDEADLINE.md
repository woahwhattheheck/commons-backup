# FERTDEADLINE — healthy-animal fertilizer overwrite rescue

Status: **source-bound candidate, default OFF / not production-activated**.

## Mechanism

The official engine stores fertilizer availability on each animal tile as a boolean. `COLLECT_FERTILIZER` consumes one visible unit by changing that boolean from true to false. At end of day, every surviving animal unconditionally receives `fertilizer_available = True` after the feed/escape check. Because the field is boolean rather than a counter, a surviving animal that enters EOD with `fertilizer_available == True` loses one collectible unit to overwrite.

Canonical V4 already enables the current-native `idle_fertilizer` owner. That owner is deliberately narrow: it inserts a literal-idle round trip only when it can preserve authored work, certify current-day physical capacity without future-sale credit, avoid future fertilizer-input use, find a safe same-return sale outlet, and return before branch/hire/EOD boundaries. However, its target filter additionally requires `fed_today == False` and `consecutive_unfed >= 1`. That historical salvage-only restriction excludes healthy animals even though their visible fertilizer has the same EOD deadline.

FERTDEADLINE changes only that target filter. It does **not** add animals, hire workers, create a scheduler/controller, alter route ownership, expand shed capacity, or claim herd-scale economics. Existing authored future `COLLECT_FERTILIZER` and `FEED` targets remain excluded by `_idle_stock_bound`; existing fertilizer `PICKUP`/`FERTILIZE` use still blocks the sale certificate; the one-idle-job ownership invariant remains intact.

## Exact current-native source

- `spatial_tempo.py` Git blob: `edbc423023479dbe2e78131495334384a87b607f`
- official engine evidence consumed by this claim: `kaggriculture.py` blob `3c202c7e...` (COLLECT clears the boolean; surviving-animal EOD resets it true)
- composer: `compose_current_fertilizer_deadline.py`

The composer is fail-closed on the exact `spatial_tempo.py` blob and one exact eligibility block. Its semantic postimage is a one-line deletion: remove the `fed_today` / `consecutive_unfed` restriction while retaining every stronger current route, stock, reservation, outlet and ownership guard.

## Required gate before activation

The package is intentionally not wired into production. A current-native execution owner must compose the generated `spatial_tempo.py`, prove OFF whole-trace identity, census natural engagements on both seats, and report at minimum: newly rescued healthy-animal collections, authored COLLECT/FEED conflicts (must remain zero), fertilizer-input cancellation, shed/carry rejection, deadline fallback count, realized fertilizer sales, own cash, rival cash and terminal margin. Zero engagement is COLD, not a reason to weaken guards. Negative economics keeps the repair source-only.

This lane is subordinate to the single V4 composition/assembly line. HERDSCALE retains BUY_ANIMAL/herd-count scaling; LABORFLOW retains generic worker assignment; CARRYBANK retains capacity hoisting.
