# SEEDGHOST — atomic PLANT ghost-row admission repair

This package lives inside the sole `main:candidates/v4` workspace. It does not create a new V4, controller, crop policy, default feature, production archive, or Kaggle submission.

## Engine seam

The pinned official interpreter (`kaggriculture.py` Git blob `3c202c7ee921da239356789e266b694635103fc4`) performs atomic same-crop PLANT validation before dispatching actors:

1. it counts the farmer row plus **every raw row** in `action["hands"]` into `plant_demand`;
2. if demand for a crop exceeds `private["seeds"][crop]`, every PLANT request for that crop is converted to PASS;
3. only after that census does `_apply_unit_action` resolve an actor position, where a surplus hand index has no position and therefore cannot execute.

So a non-existent suffix hand can be physically unable to plant yet still poison seed admission for live actors.

`ghost_plant_admission.py` repairs only that contradiction. For a crop it requires

`0 < live_demand <= available_seeds < raw_demand`

and replaces the **minimum number of latest suffix PLANT rows** with `['PASS']` needed to make the raw atomic census feasible. Vector length is preserved. Farmer/live-hand rows, market orders, non-PLANT suffix rows, crops with enough raw seeds, and genuinely over-subscribed live crops are untouched. Malformed PLANT crop arguments and invalid seed state fail closed. `enabled=False` returns the exact input action object.

This is intentionally not a generic “trim ghost hands” pass. Recent V4 work correctly established that surplus raw hand rows are engine-significant; this repair acts only where the engine itself proves the suffix actor cannot execute and the suffix PLANT is the sole cause of atomic rejection.

## Executed source and engine evidence

The source-only suite has 9 tests and passed in both normal Python and `python -O`. `check_mutants.py` rejected 4 deliberately broken semantic variants in each mode: dropping the seed-equality boundary, forgetting the live-hand count, editing the earliest rather than latest ghost row, and under-repairing excess demand.

The official-engine suite has 6 tests and passed in both modes against engine blob `3c202c7e` and offline-loader blob `23948e10`. It executes 14 official interpreter calls per mode. The causal two-seat witness is intentionally small and exact:

- 2 CARROT seeds;
- farmer + one live hand each request CARROT PLANT;
- one non-existent suffix hand also requests CARROT PLANT.

Unmodified engine behavior: raw demand is 3 > 2, so **0 plants execute and both seeds remain**. After the certified repair, the suffix row becomes PASS, raw demand becomes 2, and **both live PLANTs execute with 0 seeds remaining**. The same test passes for both seats. Separate controls prove genuine live oversubscription remains blocked and no-op cases preserve exact identity.

## Native census and parity

Evidence used authenticated workflow artifact `10175943272`, ZIP SHA256 `3a3b74936d238bf884f89a1b279f42676cda35c590f131a6a3548de52d61b4e8`, containing canonical runtime archive SHA256 `b567942e4fb4e0571ebf9f8eaaf143d4a9156df3289f09a98db37823ef4d68d9`. The tested runtime pins were `main.py` Git blob `4a8cf7bcda1f0fea231a144692cb84a779a9e73e` and `titan_runtime.py` blob `b952c9c228ecbde592bf3d2df01638677abb0d24`.

`run_native_census.py` used the official interpreter directly rather than the historical evaluator driver's invalid `len(returned_hands) <= len(live_hands)` assertion. Seeds 11, 17 and 101, both seats, completed 719 callbacks each. Across those 4,314 native candidate callbacks there were 132 callbacks with one surplus raw hand row, but **zero surplus PLANT rows and zero certified SEEDGHOST activations**. That is a reachability result, not a kill.

For seeds 17 and 101, both seats, OFF and ON were rerun independently (8 full games / 5,752 candidate callbacks total). Because there were no certified activations, every returned-action hash, complete public+own-private state trace hash, terminal score and step count matched exactly; ON changed zero actions. Scores were 105846/3741 on seed17 and 180745/3816 on seed101, mirrored by seat.

The constructed engine witness proves the repair semantics; the small native panel does **not** prove field EV or current natural engagement. Keep it default OFF until a current-source composer finds a real firing case or another candidate begins emitting poisoned surplus PLANT rows.

## Reproduce

With an authenticated native runtime artifact extracted at `$RUNTIME`:

```bash
PKG=revenue/kaggriculture/cloud-execution-lab/candidates/v4/repairs/gameplay/ghost-plant-admission
python "$PKG/test_ghost_plant_admission.py"
python -O "$PKG/test_ghost_plant_admission.py"
SEEDGHOST_NATIVE_ROOT="$RUNTIME" python "$PKG/test_official_engine.py"
SEEDGHOST_NATIVE_ROOT="$RUNTIME" python -O "$PKG/test_official_engine.py"
python "$PKG/check_mutants.py"
python -O "$PKG/check_mutants.py"
python "$PKG/run_native_census.py" \
  --runtime "$RUNTIME" --output /tmp/seedghost-census.json \
  --seeds 11,17,101 --parity-seeds 17,101
```

## Composition contract

Call `repair_ghost_plant_poisoning(observation, returned_action, enabled=...)` only at a returned-action boundary after all intended unit-action producers have finished. If changed, downstream receipt/history code must bind the repaired action, not the pre-repair object. The helper has no persistent state and does not call a producer or simulator.

This package deliberately does not patch `main.py` or `titan_runtime.py`; those shared surfaces were moving rapidly during delivery and are owned by the single-V4 composition gate. The additive helper is source-bound by executable official-engine tests and is ready for that composer when a natural/current candidate demonstrates the seam.
