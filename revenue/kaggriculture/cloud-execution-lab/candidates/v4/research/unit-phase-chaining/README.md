# TITAN V4 — Unit-phase chaining (TILEPIPE + UNITPIPE admission)

Research-only, source-bound evidence for a Kaggriculture engine seam plus the conservative, default-OFF UNITPIPE returned-action admission experiment. The same canonical package also contains separately owned UNITRECYCLE research; this TILEPIPE receipt does not evaluate or activate that policy. Nothing here changes the controller, runtime, config, feature defaults, archive, submission, or composition graph.

## Exact mechanism

Canonical engine authority: `reference/engine/kaggriculture.py` Git blob `3c202c7ee921da239356789e266b694635103fc4`.

For each player callback, the interpreter first computes one atomic same-crop `PLANT` collateral check across the farmer and every hand. It then executes the farmer (`actor 0`) and hands (`actor 1..N`) **sequentially in list order**, mutating the shared farm after every unit action. The market phase starts only after the player unit loops finish.

That makes a narrow class of same-callback, same-tile pipelines mechanically real when the later actor already owns every non-tile prerequisite:

| Earlier actor | Later actor | Source consequence |
| --- | --- | --- |
| `DIG` weed/empty structure | `PLANT crop` | later actor sees `None` and can plant immediately, subject to the callback-wide seed preflight |
| `HARVEST` mature non-ongoing crop | `PLANT crop` | harvest clears the tile to `None`; later actor can replant immediately |
| `FERTILIZE` | `WATER` | later water sees the just-written `fertilized_until_day` and receives the fertilizer watering bonus in the eligible window |
| `BUILD_COOP` / `BUILD_PASTURE` | `PLACE animal` | later actor can place onto the just-built matching structure **only if that actor already carries the animal** |

The executable oracle proves each positive witness against its reversed actor order and includes a distinct-tile negative control. It also pins the existing atomic seed rule: two WHEAT `PLANT` requests with one WHEAT seed are both converted to `PASS`; actor ordering cannot escape seed collateral.

## Converged UNITPIPE admission experiment

`unit_pipeline_admission.py` is the unique implementation delta recovered from superseded PR #12866 after this package became the canonical source-mechanism authority. #12866 is closed unmerged so V4 does not carry a second unit-order package.

The helper is deliberately much narrower than the source theorem. With `enabled=False` it returns exact action identity. With `enabled=True` it may only reorder **already-authored**, already-co-located, actor-local-inventory-neutral rows:

- empty tile: existing `PLANT -> WATER`;
- observed `WEED`, empty `COOP`, or empty `PASTURE`: existing `DIG -> PLANT [-> WATER]`.

It never invents a row, actor, movement, crop, quantity, or market order. It preserves the raw `PLANT` multiset and refuses engagement when whole-vector same-crop PLANT demand exceeds observed seeds, so the official atomic collateral rule cannot be bypassed. It also refuses inventory/service-dependent rows such as `PLACE`, `FERTILIZE`, `FEED`, `CARE`, `HARVEST`, `PICKUP`, and `DROP`; TILEPIPE's source witnesses for those operations remain evidence-only until actor-local inventory/lifecycle admission is separately proven.

This helper is **not runtime-wired** and has no activation authority.

## Current-native b567 census — COLD

The first authenticated current-native TILEPIPE/UNITPIPE gate is closed **COLD_CURRENT_NATIVE_B567**. `native_census.py` runs one seed/seat per process against native artifact `10175943272` / inner tar SHA256 `b567942e4fb4e0571ebf9f8eaaf143d4a9156df3289f09a98db37823ef4d68d9` and fails closed unless all of these exact identities match:

- official engine Git blob `3c202c7ee921da239356789e266b694635103fc4`;
- native `main.py` Git blob `4a8cf7bcda1f0fea231a144692cb84a779a9e73e`;
- native `TITAN-CONFIG.json` Git blob `3a3bef83899d3010fad623b628d9e95d9978111b`;
- canonical UNITPIPE admission helper Git blob `f02448806f66e524fdc317c23b620fde45a926c9`.

Panel: 8 fixed seeds (`17, 101, 6607, 9922999, 2026091201, 2026091207, 2026091213, 2026091219`) × both seats = 16/16 complete cells, 11,504 callbacks. The returned native action surface produced 5,124 callbacks with at least one co-located actor group and 9,342 co-located groups in total, so the cold verdict is not caused by an absence of worker co-location.

Observed source-real chain counts were all zero: `DIG->PLANT`, `PLANT->WATER`, `DIG->PLANT->WATER`, `HARVEST->PLANT`, `HARVEST->PLANT->WATER`, fresh-bonus `FERTILIZE->WATER`, and `BUILD->PLACE`. The narrower canonical UNITPIPE admission helper likewise reported `eligible_groups=0` and `changed_groups=0` across the full panel.

The detector is not cold because it is inert. Constructed controls under the same pinned engine fire `PLANT->WATER`, `DIG->PLANT->WATER`, fresh-bonus `FERTILIZE->WATER`, `BUILD_COOP->PLACE GOOSE`, and a backward pure-row reorder opportunity. The converged donor annual witness additionally proves all 3×3 mature WHEAT/CARROT/MELON `HARVEST -> PLANT -> WATER` pairs survive end of day. Reversing the middle rows to `HARVEST -> WATER -> PLANT` leaves the replacement unwatered and end-of-day refresh converts it to `WEED`. Harvested cargo remains in the executing actor's private inventory, so HARVEST is not treated as a freely reorderable pure tile operation.

Interpretation: the engine theorem is real, but this authenticated current native does not naturally author the needed TILEPIPE chain or UNITPIPE safe-pure-reorder surfaces. There is therefore no evidence-backed reason to wire UNITPIPE/TILEPIPE into runtime, defaults, config, composition, archive, or Kaggle submission from this panel.

## UNITRECYCLE boundary

Merged UNITRECYCLE is a different consumer of same-callback evidence: it considers replacing a strict later redundant source row with inventory-neutral `CARE` under its own fail-closed custody rules. This TILEPIPE `NATIVE-CENSUS.json` does **not** claim UNITRECYCLE is cold, safe, profitable, or promotable; its natural-engagement/economics gate remains independently owned.

## What this does not authorize

- No same-callback market credit. Unit actions happen before `BUY_SEED`, `BUY_PRODUCT`, `BUY_ANIMAL`, `HIRE`, and other market commits, so a unit pipeline may use only inventory/seeds/workers already physically present before the callback.
- No cross-actor inventory transfer. A later `PLACE`/`FERTILIZE`/`FEED` must be collateralized by that later actor's own carried inventory unless an existing engine operation moved it earlier.
- No immediate annual-crop harvest. `HARVEST` rejects a plant whose age is below that crop's `first_yield_day`; a legal `HARVEST -> PLANT` chain begins from an already-mature non-ongoing crop with positive yield.
- No blanket instruction to co-locate workers. Movement, hire cost, lost parallelism, route displacement, and terminal economics are outside this source theorem.
- No new scheduler/controller. This package remains the shared evidence/admission authority for existing LABORFLOW/route/composition owners to consume.

## Validation

From this directory on a complete Commons checkout:

```bash
python -B test_unit_phase_chaining.py
python -O -B test_unit_phase_chaining.py
python -B test_unit_pipeline_admission.py
python -O -B test_unit_pipeline_admission.py
python -B test_native_census.py
python -O -B test_native_census.py
python -B unit_phase_chaining.py --out /tmp/tilepipe.json
python -B -m py_compile unit_phase_chaining.py unit_pipeline_admission.py native_census.py test_unit_phase_chaining.py test_unit_pipeline_admission.py test_native_census.py
```

To reproduce one authenticated field cell after extracting artifact `10175943272`:

```bash
python -B native_census.py cell --package /path/to/extracted/b567-runtime --seed 17 --seat 0 --output /tmp/tilepipe-17-0.json
```

Run each seed/seat in a fresh process, then aggregate the 16 cell reports with `native_census.py aggregate ...`. `NATIVE-CENSUS.json` is the checked-in panel receipt.

The source checker fails closed if the canonical engine blob moves, if farmer/hand execution order changes, if hand iteration is no longer literal `enumerate(hands_actions)`, if market moves ahead of the unit phase, or if the atomic PLANT preflight changes. The UNITPIPE admission tests additionally pin OFF identity, same-site-only eligibility, market/unrelated-row preservation, global seed collateral, destructive-state refusal, and refusal of inventory/service-dependent groups. The native scanner independently pins the artifact, `main.py`, config, and UNITPIPE admission helper.

## Reopen gate

Current b567 TILEPIPE/UNITPIPE is closed cold. Re-run this gate only when a relevant producer identity changes — e.g. native artifact/`main.py`, `TITAN-CONFIG.json`, the UNITPIPE admission helper, or the route/action authoring surface — or when another source-authenticated producer begins returning the required co-located multisets. A new positive source witness alone is not activation evidence.

Disposition: `SOURCE_MECHANISM_CONFIRMED_ADMISSION_DEFAULT_OFF_COLD_CURRENT_NATIVE_B567`.
