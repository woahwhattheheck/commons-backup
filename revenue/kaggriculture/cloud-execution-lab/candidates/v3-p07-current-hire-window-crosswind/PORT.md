# Deterministic V3 one-tree port packet

This successor is deliberately **not** wired into the canonical runtime or the
new `candidates/v3` tree by this branch. It is an additive, exact-source-bound
port packet for the one-tree owner to consume after that tree exists.

## Required files

Copy these files together into the materialized V3 overlay:

- the preserved P07 `joint_actors.py`, exact Git blob
  `129e70bc8f54101726e3a1794d4480749fd88408`;
- `current_hire_window.py`;
- `current_hire_joint_actors.py`.

Do not silently rewrite the preserved P07 module. The successor imports it and
changes only window admission plus the observed-actor loop bound.

## Default-off key

Add one feature key with a false default:

```python
p07_current_hire_existing_workers: bool = False
```

At the existing post-`SpatialTempo.transform`, pre-commit P07 callsite, select
exactly one reconciler:

```python
if features.p07_current_hire_existing_workers:
    from current_hire_joint_actors import reconcile
    result, spatial.joint_report = reconcile(spatial, obs, result, controller)
elif features.joint_actors:
    from joint_actors import reconcile
    result, spatial.joint_report = reconcile(spatial, obs, result, controller)
```

The new key must remain false in all-off and released configurations until a
candidate-action panel records at least one accepted live swap and a matched
own-cash panel clears promotion.

## Required port gates

1. Re-run `verify_sources.py`; a moved source pin is a hard stop.
2. Run all tests in `test_current_hire_window.py` against the materialized tree.
3. Prove all-off archive identity against the one-tree base.
4. With only this key enabled, retain action-level activation logs and paired
   candidate/control terminal own cash by opponent, seed, and seat.
5. Reject promotion on zero activations, any timeout/invalid action, any
   non-pair unit-byte drift, any market-byte drift, or any negative holdout
   own-cash delta not explicitly adjudicated.

No Kaggle upload is authorized by this packet.
