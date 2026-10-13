# TITAN V4 lockstep return bridge

This package closes the orphaned current-native wiring lane left when the earlier LOCKSMITH session disappeared before publishing source. It does **not** recreate or claim custody of that unpublished implementation. The successor composes only already-landed authorities:

- ESTUARY `effective_flow_bounds.py`, Git blob `e24dd03a88a71ba4cf6f8d5da1082b89490b5a94`.
- CROSSCURRENT `join_queue_contract.py`, Git blob `ac91d3c65deeabadaa60ee83c4a7a84286849150`.
- FLOWPROOF's independent acceptance of the ESTUARY bound remains the evidence owner; this package does not duplicate it.

## Native contract

The bridge is per-agent and default-OFF. On a successfully completed returned action it stores only the public flow observation, the exact returned action, and configuration needed to interpret the adjacent transition. On the next observation it asks ESTUARY for conservative effective opponent-flow bounds and consumes only LOWER-bound confirmed net sells for the seven products owned by the frozen seller (`CARROT`, `TOMATO`, `STRAWBERRY`, `MELON`, `EGG`, `MILK`, `WOOL`). WHEAT/FERTILIZER are never routed through the seller debt ledger. This is a hard producer-ownership boundary, not a missing branch: `scheduler.PRODUCTS` excludes them, so a WHEAT flow signal cannot authorize this component to invent or move a WHEAT sale. The late WHEAT loss episode `108029864` is therefore a negative applicability regression for RETURNBRIDGE unless a separate producer-owned future-WHEAT sale authority is landed.

A proposal may pull at most one already-owned future seller tranche into the current raw market row 0. It requires exact post-unit shed stock, exact native `planned` + `pending` debt, literal empty/no-op row 0, and CROSSCURRENT certification that no other raw slot moves. It additionally rejects active-prefix resource orders and later same-product SELL/BUY_PRODUCT rows because slot preservation alone does not certify their economics.

Proposal is side-effect free. Commit revalidates exact baseline/candidate digests and the exact native debt snapshot before changing anything. An accepted pull decrements the specific future `planned` tranche and `pending`, then calls the existing `_commit_seller_state()` so the completed checkpoint matches the candidate action. Any drift/tamper returns the exact baseline action with no debt mutation.

## Exact returned-action boundary

`compose_native_return_bridge.py` binds the bridge around the existing outer `main.py::agent` timer:

1. `bridge.observe(...)` before `instance.act(...)` consumes only the prior completed transition.
2. `instance.act(...)` produces the full late-guarded native action.
3. `bridge.propose(...)` sees that exact baseline and mutates no native state.
4. `bridge.commit(...)` runs immediately afterward **inside the same outer timer**. If the timer cancels after a commit, canonical `main.py` already discards `_INSTANCE`, so committed bridge/seller state cannot leak into the fallback path.

The composer refuses source drift before its first write. Audited current inputs are `main.py` blob `4a8cf7bcda1f0fea231a144692cb84a779a9e73e`, `titan_runtime.py` `6d9720f4aa1e6b46e92ee5183897074d8e9ea5a0`, `frozen_selected.py` `fc7baf5c179818a55037f6a61d92984d81d1a21c`, `scheduler.py` `a483b24dd72b580d7d8811636b54d2d44f391575`, and `TITAN-CONFIG.json` `3a3bef83899d3010fad623b628d9e95d9978111b`.

The materialized package gets a `lockstep_join: false` feature, the bridge module, and byte-exact copies of the two authority helpers. This source package does not modify production, defaults, archive, workflows, or Kaggle submissions.

## Executed focused controls

Authored bytes were run locally with:

```bash
python -B -m unittest -v test_native_return_bridge.py test_compose_native_return_bridge.py test_wheat_boundary.py
python -O -B -m unittest -v test_native_return_bridge.py test_compose_native_return_bridge.py test_wheat_boundary.py
```

Both modes: **23/23 PASS**, zero failures/errors/skips after correcting one test-only bookkeeping expectation found by the first run. Controls cover cold identity, adjacency/episode reset, mutation-free proposal, exact debt/checkpoint commit, stale-plan/tampered-candidate rollback to baseline, row-0 occupancy, later resource/same-product rejection, exact post-unit binding, inner-deadline non-evidence, partial debt, explicit rejection of a certified WHEAT signal at the native seller boundary, exact authority-module namespace binding for future-annotations dataclasses, composer source anchors, default-OFF config, and drift/duplicate-anchor refusal.

The live runtime pin was refreshed after canonical PR #12788 changed only the completed-module cache-hit namespace binding; the feature/consumer anchors used by this composer are unchanged. These are source/semantic integration controls, not an EV or promotion result. No full-game strength, gauntlet gain, or enable recommendation is claimed. A future activation gate must measure economics against real opponents and current composed V4; this package only makes that gate executable without corrupting native action/debt custody.
