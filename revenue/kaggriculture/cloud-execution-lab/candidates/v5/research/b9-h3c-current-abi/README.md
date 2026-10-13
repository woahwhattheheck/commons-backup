# V3.1 B9 terminal fertilizer + H3c goose rescue — current ABI

Additive research recovery under `V5-V31-R04-POLICY-FAMILY-RECOVERY-WIDE`.
It changes no current runtime/default/config/release pointer and submits nothing.

## Exact submitted sources

Authority is submitted V3.1 commit `a90d888f03987ef0b35cfd20ec3519c6144db08a`:

- `candidates/v3/overlay/b9_terminal_fertilizer.py` Git blob `ed8d6923541e700c3a0ae4b93695bbd56455a3b6`.
- `candidates/v3/overlay/h3c_goose_eod_cap_rescue.py` Git blob `2044d6cf1e0c51f95027229863f910aa43ac7008`.

`outer_wrappers_current.py` authenticates those exact bytes with the Git blob algorithm before importing them. No gameplay theorem is copied into the adapter.

## Current selected-action seam

`B9H3CCurrentABI.transform(observation, configuration, selected)` takes an already-selected action. It never calls a producer or controller.

The submitted outer order is preserved:

1. **B9 terminal fertilizer** — on standard 720-step / 24-turn-day configuration, literal PASS at steps 716/717 may become `COLLECT_FERTILIZER` for represented workers already on a shed-adjacent animal tile with public fertilizer available. Only if that episode state observed a successful collection, step 718 stable-partitions `SELL FERTILIZER` behind other rows **inside the executable market prefix**, preserving the raw tail indexes. Retry/rewind and invalid terminal configuration reset B9 state exactly like the submitted wrapper.
2. **H3c goose EOD cap rescue** — on a standard hour-23 configuration, literal `COLLECT_FERTILIZER` may become `HARVEST` on the same already-occupied mature GOOSE only when a real next-day production clip is proved, the animal is fed/cared, fertilizer is collectible, stacked-worker ambiguity is absent, same-turn rival-dependent market inflows are absent, and a conservative whole-farm capacity bound proves every unit still fits after EOD auto-drop.

Both feature bits require exact `bool` and default `false`.

## Contracts

```bash
cd revenue/kaggriculture/cloud-execution-lab/candidates/v5/research/b9-h3c-current-abi
python -B -m py_compile outer_wrappers_current.py test_outer_wrappers_current.py
python -B -m unittest -v test_outer_wrappers_current.py
python -O -B -m unittest -v test_outer_wrappers_current.py
```

The suite locks exact donor blobs, default-OFF identity, B9 collect→terminal prefix partition, invalid-config and retry state reset, a real H3c EOD-overflow activation, H3c market-inflow/capacity vetoes, and explicit B9→H3c order.

## Promotion boundary

This carrier makes exact submitted behavior callable from current V5. It is not promotion authority. A later composition must bind it to the single current selected-action finalization path without a second producer, then run matched both-seat current-V5 economics. Historical V3.1 uplift remains motivation only.
