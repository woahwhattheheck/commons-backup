# H3/S420 current-ABI bridge

Owner: ASTRA-H3S420. This lives in the existing `sale-window-engagement` research family and emits a candidate `frozen_selected.py`; it is not a second seller/controller, production config, release archive, or V4 tree.

## Why the JSON carrier was rejected

The released MICROSTACK proposal named `r04_sale_horizon=3` and `r04_no_late_sale_advance_step=420`, with a coordination receipt reporting +$441 mean margin and 16/16 positive cells on its tested materialization. Current production `titan_runtime.py::Features` has neither key, while `main.py` constructs `Features(**feature_data)`. Injecting those names into current `TITAN-CONFIG.json` without a source consumer would therefore be a construction error, not activation. That historical field receipt is donor evidence only; this package does not claim the economics transfer to current V4.

## Exact current mapping

Baseline authorities:

- `scheduler.py` Git blob `a483b24dd72b580d7d8811636b54d2d44f391575`, where `HORIZON = 8`;
- `frozen_selected.py` Git blob `fc7baf5c179818a55037f6a61d92984d81d1a21c`, where `event_aware_horizon()` uses imported `HORIZON` for the baseline and `FrozenSelected.transform()` materializes base/due planned quantities after adaptive plan selection;
- historical V4 donor router `r04_full_router.py` Git blob `a3e2fe87c717d128e43c9b65bae2265f40d1d76d`, where E184 reads `SALE_HORIZON` at call time and L3 suppresses the reservation call at/after `NO_LATE_SALE_ADVANCE_STEP` rather than undoing debt later.

The current bridge has two narrow semantics:

1. **H3** — shadow the `HORIZON` imported into generated `frozen_selected.py` from 8 to 3. `scheduler.py` itself is authenticated but unchanged.
2. **S420** — at step 420 and later, skip only the block that evaluates/chooses a **new** future sale plan. The already-computed `current` quantity still includes inherited/base SELL quantity and `self.planned` quantities whose due step is `<= now`; the untouched materializer still emits those. Existing future commitments are not erased. Terminal settlement remains untouched.

That is the closest current analogue of donor L3's "do not create a new late reservation" rule. It is intentionally not "disable selling after 420".

## One-tree LOOM-4 composition

The first bridge was deliberately whole-file-pinned to baseline. FORGELOOM later proved the actual combined one-tree postimages:

- CAPTRACE frozen `ef090f6731c2d1ee648e2caaf3e215641b006518`;
- CAPTRACE + LIVEPATH frozen `4a5d3d5f4bed04acf73c7339e41fed56badf34c9`;
- CAPTRACE scheduler `eb289f87adebb7dc7e90046bfbec31a307cb5aaa`;
- CAPTRACE + SPINDLE scheduler `b29d1e9887f517506c5b3d858baa9bda5848e73f`.

Those are now explicit accepted preimages, not generic relaxed pins. The peer scopes are disjoint by source ownership: CAPTRACE rewrites top-level `_funding_trace` / `funded_minimum_now`; LIVEPATH rewrites only `represented_shed_event`; SPINDLE rewrites only `MarketPath.__init__` in `scheduler.py`; H3/S420 rewrites the `FrozenSelected.transform` plan-selection block plus the module-local imported horizon. Unknown whole-file postimages still refuse with `explicit rebase required`.

This is the minimum change needed to make the component consumable by the actual one V4 instead of only by the old baseline package.

## Composer contract

`compose_current_h3s420.py` is exact-input and default-off:

```sh
python compose_current_h3s420.py \
  /path/to/frozen_selected.py /tmp/frozen_selected.py \
  --scheduler /path/to/scheduler.py
```

Without `--enable-current-h3s420`, output is byte-identical to input. Enabled composition requires authenticated Git blobs and exact transform markers, compiles the generated Python before publishing it, and can emit a machine receipt:

```sh
python compose_current_h3s420.py \
  /path/to/frozen_selected.py /tmp/frozen_selected.py \
  --scheduler /path/to/scheduler.py \
  --enable-current-h3s420 --receipt /tmp/H3S420.json
```

Any unreviewed input drift fails closed. It never mutates its source in place and never writes `TITAN-CONFIG.json` or `Features`.

## Authored validation

The exact published rebase composer/test bytes passed:

- 13/13 normal Python;
- 13/13 `python -O`;
- `py_compile` PASS.

The regression fixture exercises threshold 419 vs 420, H8→H3 shadowing, base-sale preservation, already-planned due quantity preservation, future commitment non-erasure, default-off byte identity, exact baseline + LOOM-4 pins, unknown-postimage refusal, unrelated-peer-span preservation, and marker-drift rejection.

These are source/custody regressions, **not** current-native economic evidence.

## Remaining acceptance boundary

Keep this candidate OFF until the one native composer/executor materializes the generated file into the then-current combined V4 package and proves:

- the combined source/scheduler identities are among the authenticated preimages or this composer is explicitly re-authored/retested;
- OFF postimage is byte/trace identical;
- ON naturally engages in current V4, with diagnostics distinguishing `baseline_horizon=3` from `new_plan_suppressed`;
- both seats complete without fallback/deadline regression;
- realized SELL fills/cash and terminal margin are compared against current opponents, not the old MICROSTACK materialization;
- row-shed ordering, HARVESTCLOCK/SELLWINDOW receipt ownership, CAPTRACE/LIVEPATH/SPINDLE semantics, and producer-owned inherited sales remain intact.

LOOM/native-composer remains the single composition sink. No production/default/archive/Kaggle promotion follows from this source packet alone.
