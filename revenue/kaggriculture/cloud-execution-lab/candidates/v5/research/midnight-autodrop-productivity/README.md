# V5 midnight auto-drop productivity

Research carrier for `GPT-V5-MIDNIGHT-AUTODROP-PRODUCTIVITY`.

## Engine theorem

Pinned engine Git blob `3c202c7ee921da239356789e266b694635103fc4` executes unit actions, market actions, town consumption and plant decay, then on the final callback of each day calls `_end_of_day()`. That routine drops **every** farmer/hand inventory into the shed up to `shedCapacity` regardless of worker position, then resets the main farmer position, deletes all hands, resets hires, and replaces private inventories with one empty main inventory.

Therefore a final-callback `PASS`, `DROP`, or movement has no positional value after that callback. A returned action can reclaim that unit slot only if an immediately productive action is legal at the worker's *current* tile and doing so cannot displace pre-existing carried goods at the automatic drop.

## Candidate

`midnight_salvage.apply()` is deliberately narrow in *authority* but wide over the safe last-tick opportunity:

- candidate only: no production runtime/default/config/archive/Kaggle mutation;
- final callback only (`step % turnsPerDay == turnsPerDay - 1`);
- only replaces `PASS`, `DROP`, `NORTH`, `SOUTH`, `EAST`, or `WEST`;
- productive actions: urgent `FEED`, ready animal `HARVEST`, ready `COLLECT_FERTILIZER`, already-fed `CARE`, or ready **ongoing** crop `HARVEST`;
- one-shot WHEAT/CARROT/MELON harvest is intentionally excluded in v1 because clearing the tile immediately exposes it to the same EOD weed-spawn pass;
- same-tile duplicate workers are not double-spent;
- no market edits and no path replanning.

The capacity certificate is aggregate and conservative. It reserves room for:

1. all goods already in every worker inventory,
2. output from other already-authored `HARVEST` / `COLLECT_FERTILIZER` actions,
3. the upper bound of executable-prefix `BUY_PRODUCT` / `BUY_ANIMAL` shed inflow,
4. all candidate-added harvest/fertilizer output,

minus candidate WHEAT consumed by `FEED`.

If those goods do not all fit, the transform refuses the rewrite, so dict/worker drop order cannot cause an old carried good to be displaced by the experiment.

## Local checks

```bash
python candidates/v5/research/midnight-autodrop-productivity/test_midnight_salvage.py
python -O candidates/v5/research/midnight-autodrop-productivity/test_midnight_salvage.py
```

Both suites must pass before any engine screen.

## Engagement-first screen

Do **not** burn a broad matrix until engagement is proven.

1. Run canonical current V5 and this wrapper on the same known-loss / recent representative traces.
2. Record wrapper `diagnostics()` plus every changed report: step/day, unit index/position, original action, replacement, reason, aggregate capacity certificate.
3. If zero engagements, classify `NO_ENGAGEMENT` and retire v1 without runtime integration.
4. If engagements exist, run matched A/B, both seats, same seeds/opponents. Report final score/cash delta plus engagement count by `prevent_escape`, `harvest_ready_animal`, `collect_before_refresh`, `care_after_feed`, `reset_unfed_counter`, and `harvest_ready_crop`.
5. Only an observed economic win earns a production-hook proposal. Production route/path owners remain authoritative.

`main.py` is a source-tree wrapper over canonical root `main.py`; it records bounded diagnostics and applies no other policy.
