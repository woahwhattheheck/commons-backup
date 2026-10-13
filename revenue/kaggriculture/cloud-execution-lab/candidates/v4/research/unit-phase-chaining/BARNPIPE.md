# BARNPIPE — same-callback animal placement/service chaining

## Recovery status

This is a recovery of the stale `ASTRA-BARNPIPE-PLACE-SERVICE-CHAIN` claim in the existing canonical `research/unit-phase-chaining/` package. The original claim had no thread replies or durable GitHub artifact when recovered. No sibling V4/package/controller is created.

Research/evidence only. Nothing here changes a returned action, runtime/default/configuration, `COMPOSITION.json`, `INTEGRATION.json`, archive, or Kaggle submission behavior.

## Source custody

Pinned existing chaining oracle Git blob: `unit_phase_chaining.py@4f3be59d7f29024bda355933c61ebf3cad49037d`.

BARNPIPE does not import that dependency through ambient Python module resolution. It first reads the canonical sibling path as bytes, authenticates the exact Git object ID, then compiles/executes **that captured byte buffer** under a private module name. A drifted replacement is rejected before execution. The authenticated chaining oracle in turn pins official engine Git blob `3c202c7ee921da239356789e266b694635103fc4`, authenticates engine bytes before source analysis, and loads only the selected exact engine AST used by its witnesses. BARNPIPE additionally compiles the exact `_daily_refresh_animals` definition from the same authenticated engine source.

## Source mechanism

The canonical interpreter applies one player's units sequentially: main farmer first, then hands in list order, all against the same mutable `farm` and `private` state, before market processing. Therefore a tile mutation by actor N is immediately visible to actor N+1 in the same callback.

Animal-specific consequences:

- `PLACE <animal>` consumes exactly one animal from the **placing actor's own inventory** only when the actor stands on the matching empty structure (`GOOSE→COOP`, `COW/SHEEP→PASTURE`). It immediately replaces that structure dict with `_new_animal(...)`.
- A later co-located `FEED` now sees that new live animal tile. It consumes one WHEAT from the **feeding actor's own inventory** and sets `fed_today=True`.
- A still-later co-located `CARE` sees the same animal and sets `cared_today=True`.
- Starting from an empty owned tile, four ordered actors can therefore execute `BUILD_{COOP|PASTURE} → PLACE → FEED → CARE` in one callback.

There is no cross-actor inventory sharing. Order and co-location are the mechanism: FEED/CARE before PLACE silently no-op, PLACE before BUILD does not retroactively succeed, a later FEED cannot spend WHEAT carried by an earlier actor, the wrong structure refuses PLACE, and service actions on a different tile do not reach the animal.

## Placement-day care bonus

`_daily_refresh_animals` is part of canonical EOD. All three animals have first-yield delays greater than one day (GOOSE 4, COW 8, SHEEP 6), so this package does **not** claim placement-day production.

On placement day, if the same callback performs PLACE→FEED→CARE, EOD sees both `fed_today` and `cared_today`. No production occurs yet, but EOD sets `pending_care_bonus += 1` and clears the daily feed/care flags. If the animal is fed on following days without any later CARE, that one pending token survives until the first production refresh. On the first production day, canonical refresh pops the pending token because the animal is fed, producing `base 1 + bonus 1 = 2`; an otherwise identical animal without placement-day CARE produces only 1. The witness executes the exact `_daily_refresh_animals` source for GOOSE, COW, and SHEEP.

## Files and evidence

- `barnpipe_place_service.py` captures/authenticates the canonical `unit_phase_chaining.py` bytes before execution, then reuses its engine-blob authentication, interpreter-order AST proof, and exact `_apply_unit_action` subset. It additionally compiles the exact source `_daily_refresh_animals` function into that authenticated namespace.
- `test_barnpipe_place_service.py` checks dependency/source drift plus all three animals across forward chains, order reversals, actor-local animal/WHEAT custody, wrong structure, distinct tiles, placement-day EOD banking, first-production bonus consumption, engine drift, and research-only policy boundaries.

## Promotion boundary

This proves a source-real mechanic and exact state transition, not that current V4 naturally authors these multi-actor rows or that doing so beats competing uses of hands, feed, structures, or hire capital. Any scheduler/admission policy needs a separate current-native opportunity census and economics gate. Until then BARNPIPE remains evidence only.
