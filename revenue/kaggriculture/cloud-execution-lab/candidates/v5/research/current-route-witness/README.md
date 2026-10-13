# Current route witness — immutable committed-receipt authority, one tape capture

This V5 provenance helper closes the future-route seam shared by recovered V3.1 selected-action transforms. B5/JIT needs the exact **step+1** authored action; H4/market recovery needs a bounded ordered future window. Those consumers must not call a second producer, reconstruct a legacy R04 tape, or perform repeated live reads that can mix route snapshots.

The trust root is the immutable entrypoint receipt published with the **current committed selected action**, not raw `controller.cur` and not an ad-hoc route string. The canonical receipt shape is exactly:

```python
{
    "route_step": step,
    "last_step": step,
    "player": observation["player"],
    "route": committed_route_id,
}
```

For a current selected-action transform, `route_step == last_step == observation["step"]` and the receipt player must equal `observation["player"]`. Carried recovery receipts whose route originated on an earlier callback remain valid entrypoint recovery state, but they are **not** current producer authority for this helper until the current producer commits a selected action. Missing, extra-key, malformed, stale, gapped, or cross-player receipts fail closed.

```python
window = bind_current_route_window(
    controller,
    observation,
    completed_route_receipt=entrypoint_route_receipt,
    lookahead=8,
)
```

The helper captures and canonicalizes exactly `controller.R[receipt["route"]]` once and rebinds that same route after capture. Raw `controller.cur` is deliberately ignored: if selected action A committed and `cur` has already moved to an interrupted proposal B, the witness binds A or fails for another reason; B never becomes authority.

Schema `titan-v5-current-route-window-v3` binds the full portable authority into `window_sha256`: route source, concrete controller type, route id, immutable receipt provenance (`route_step`, `last_step`, `player`), current step/index, current worker cardinality, route length, SHA-256 of the full captured route, requested lookahead, and ordered row receipts. This prevents identical route/row bytes from replaying under a different player, worker envelope, controller identity, or requested span.

Each row records its authored step, worker cardinality, detached canonical action bytes and action SHA-256. The full-route digest deliberately covers bytes outside a small requested window, and returned actions are reconstructed from canonical JSON so later controller/tape mutation cannot change an already-published witness.

`bind_current_route(..., completed_route_receipt=...)` derives the strict step+1 B5 view from an H1 capture and additionally requires the next authored row to have the exact current worker cardinality. `bind_b5_kwargs` emits only `next_authored` + `next_authored_step` for `B5CurrentABI.transform`. Wider consumers use the same `CurrentRouteWindow`; no feature-local tape oracle is needed.

The helper never calls `controller.act`, changes `cur`, edits route bytes, selects a policy, or imports gameplay code. It fails closed on malformed actor identity, non-plain clock values, invalid private worker cardinality, missing/replaced/drifting authorized routes, non-JSON route bytes, malformed authored actions, route exhaustion, invalid receipt authority, or invalid lookahead.

This is source/evidence plumbing only. It does not change runtime defaults, `TITAN-CONFIG.json`, archive pointers, release authority, or Kaggle submission. The intended one-V5 composition is: current producer commits selected action + immutable entrypoint route receipt -> one authenticated route-window capture -> recovered selected-action transforms -> existing matched-economics/composition/release gates.

Focused contracts:

```bash
python -B -m py_compile current_route_witness.py test_current_route_witness.py test_authority_digest.py
python -B -m unittest -v test_current_route_witness.py test_authority_digest.py
python -O -B -m unittest -v test_current_route_witness.py test_authority_digest.py
```
