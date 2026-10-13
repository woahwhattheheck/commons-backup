# Native sale-window experiment wiring

Owner: ASTRA-SELLWINDOW. Shared home and paired economic oracle: HARVESTCLOCK. This is one package in canonical `main:candidates/v4`, not another agent/controller or V4 branch.

## What is delivered

`native_sale_window.py` exposes `NativeSaleWindow(native_main, policy, enabled=True).agent`. The callback signature is `policy(observation, configuration, selected_action) -> action`. Inputs and changed outputs are detached. The existing native factory constructs the only producer/runtime. The hook runs after native final pressure, inside `_finish_production` and before quadrant/spatial/history receipt commits. The outer observer records the exact returned object without changing it.

Disabled mode returns the native callable itself and does not modify its factory. Enabled mode requires an explicit source-backed callback and a matching native entrypoint/finalizer binding. It does not modify `Features`, `TITAN-CONFIG.json`, the production runtime, or any release archive. Ordinary callback/shape errors fail closed with a recorded error. `BaseException`, including native deadline cancellation, is not swallowed.

Only selected sale-only goods may change. Unit commands, unrelated fields, non-target goods, raw market positions, the inherited economic/funding prefix, and the clipped suffix remain unchanged. The engine's minimum raw cap of one is respected. This is an ownership/shape gate, not a profitability certificate: a sale can still have future economic consequences.

Each call records callback execution, proposal acceptance, accepted-prefix change, actual-return match, actual-return-prefix change, errors and native status separately. A proposal discarded by fallback is not reported as a returned change. The pure adapter never invents fills. The runner uses HARVESTCLOCK's exact `sale_window.py` blob `20e623722fbb3f8a9cdb71add009a9f68756819d` for full-interpreter successful-fill observations. That independently authored oracle is included byte-identically in this same home; it is not reconstructed historical sellby15 code.

## Executed gates

21 tests passed normally and under `python -O`. Eight semantic faults per mode were rejected by assertions, not syntax/import failure. Constructed positive controls exercised the real native finalizer and matched direct official-engine transitions in both seats. The deadline-discard case is a white-box fixture, not a naturally observed timeout.

Twelve complete native games covered seed 17, both seats, baseline/disabled/identity modes, and normal/optimized Python. All 8,628 native turns completed without fallback. The complete action-and-state trace was identical across all six mode/interpreter combinations for each seat. The opponent was the pinned official starter. These are repeated wiring controls on one seed, NOT a twelve-game independent strength panel. Identity callbacks intentionally make no sale-time intervention.

`NATIVE-WIRING-RESULTS.json` records source bindings, full raw-record SHA-256 values, trace digests, and limits. Full raw records are retained in the associated conversation evidence ZIP; the repository receipt is compact. No GitHub CI success is claimed.

## Reproduce

Recover workflow artifact 10175943272 from `woahwhattheheck/commons`. Unpack `checked-package/exports/titan-current.tar.gz` into a scratch runtime directory. Its SHA-256 must be `b567942e4fb4e0571ebf9f8eaaf143d4a9156df3289f09a98db37823ef4d68d9`. The runner verifies all 110 regular archive members against that directory before importing it. Use the artifact's `final-pressure-runtime/checks/reference` as the reference directory. The transfer metadata calls 109 of these runtime files; the runner reports the actual 110 regular archive members, not an inferred count.

From this package directory:

```sh
export TITAN_NATIVE_ROOT=/absolute/path/to/unpacked-b567
export TITAN_REFERENCE_ROOT=/absolute/path/to/final-pressure-runtime/checks/reference
python test_native_sale_window.py
python -O test_native_sale_window.py
python run_native_wiring_faults.py --output /tmp/native-wiring-faults.json
python run_native_wiring.py \
  --native "$TITAN_NATIVE_ROOT" --reference "$TITAN_REFERENCE_ROOT" \
  --archive /absolute/path/to/checked-package/exports/titan-current.tar.gz \
  --seed 17 --seat 0 --mode identity --output /tmp/native-wiring-identity.json
```

Repeat the last command for each seat and mode (`baseline`, `disabled`, `identity`), and both normal Python and `python -O`. The runner is serial and standard-library-only; no network access or host-owner compute is needed. It observes the complete official interpreter, not a simplified transition model.

## Remaining acceptance boundaries

Historical `r04_sellby15` source and its original -86 gate have not been recovered. Nothing here is represented as a test or reconstruction of that policy. HARVESTCLOCK retains donor custody and economic acceptance. This work completes the complementary native activation/receipt-lifecycle component, not the historical lane's profitability decision.

A recovered policy must be adapted explicitly to the market-only callback, identified by source, and run through the shared paired oracle with nonzero realized engagement. Do not run the legacy R04 materializer. Later KEEL/WEAVE native compositions must revalidate the main/finalizer binding explicitly; a mismatch deliberately fails rather than stacking blindly. The outer journal adds experiment overhead outside native `main.agent`'s timer, so this is not a hosted timing certificate. Defaults and Kaggle release remain untouched.
