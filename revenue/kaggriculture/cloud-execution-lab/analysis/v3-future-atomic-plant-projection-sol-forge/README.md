# TITAN V3 — future atomic PLANT projection repair

Operation: `TITAN-V3-FUTURE-ATOMIC-PLANT-PROJECTION-20260910-01`

## Exact defect

On `main@3854f1cc46340f5099ade910e2cfc7b36606425e`, `scheduler.py`
blob `a483b24dd72b580d7d8811636b54d2d44f391575` has two different unit-stage
models:

* `post_units()` pre-counts all same-crop `PLANT` requests and blocks the entire
  crop when demand exceeds seed stock, matching the official interpreter;
* `SellScheduler.receipt_profile()` sends each actor from every future route row
  directly through `_apply_unit_action`, which makes the first legal request
  consume a scarce seed before later requests are seen.

The pinned official engine blob
`3c202c7ee921da239356789e266b694635103fc4` is explicit: every farmer/hand
request for an oversubscribed crop becomes `PASS` before any unit action runs.
A one-seed/two-planter row therefore creates zero plants and retains the seed.
The current future projection instead creates one plant and consumes the seed.

This is score-facing rather than cosmetic. `receipt_profile()` supplies the
`capacity_ok` predicate to SELL optimization. The focused predecessor witness
uses a 99/100 shed and a carried cow: the false sequential plant blocks a later
pasture and `PLACE`, so the cow falls into the shed at end of day and makes the
projected SELL plan infeasible. Under official atomic semantics the pasture and
placement succeed, the shed remains 99/100, and the same plan is feasible.

## Repair packet

`materialize.py` is a disconnected, fail-closed materializer. It verifies the
exact scheduler and engine Git blobs, introduces one shared
`_apply_unit_packet()` primitive, routes both current-step `post_units()` and
future `receipt_profile()` packets through it, compiles the candidate, and emits
an immutable JSON receipt. It never edits `scheduler.py` in place.

`test_materialize.py` provides source-bound predecessor killers for:

* oversubscribed same-crop all-or-nothing admission;
* exact-supply actor-order parity;
* mixed-crop independent blocking;
* action nonmutation;
* the old sequential counterexample;
* the 99/100 shed → SELL-feasibility causal witness;
* one direct mechanics callsite, shared by current and future paths;
* deterministic materialization, source nonmutation, and drift rejection.

`route_census.py` separately binds current Arlene blob
`bdb9cf58148a3c7961c085f4902759537decabf6`, constructs its route bank, and
inventories every row with two or more same-crop `PLANT` requests. A nonzero
census establishes only the necessary authored-route precondition (`ROUTE_RISK`);
it does not establish insufficient live seed stock, returned-action activation, or
score lift. `test_route_census.py` adds six deterministic parser, crop-isolation,
nonmutation, and fail-closed contracts.

Run from this directory's parent lab root:

```bash
python analysis/v3-future-atomic-plant-projection-sol-forge/test_materialize.py
python analysis/v3-future-atomic-plant-projection-sol-forge/test_route_census.py
python analysis/v3-future-atomic-plant-projection-sol-forge/materialize.py \
  --output /tmp/titan-future-atomic/scheduler.py \
  --receipt /tmp/titan-future-atomic/RECEIPT.json
python analysis/v3-future-atomic-plant-projection-sol-forge/route_census.py \
  --output /tmp/titan-future-atomic/ROUTE-CENSUS.json
python -m py_compile /tmp/titan-future-atomic/scheduler.py
```

## Boundary and disposition

This packet changes no canonical runtime, configuration, archive, release
pointer, provider, Kaggle submission, SELL objective, target domain, quantity,
order priority, or active purchase-fill model. Historical closed PR #11746 is
credited for the earlier FrozenSelected audit and minimized causal idea; it did
not repair current `scheduler.receipt_profile()` and its hosted workflow failed
before the audit ran because the then-current runtime closure could not import
`observed_clone`.

Disposition is `SOURCE_REAL_ACTION_UNMEASURED`. Promotion requires a fresh-main
port after the import-closure repair, candidate-returned-action activation, and a
matched both-seat current-control panel with positive own-cash mean,
nonnegative median, no new losses, and no negative opponent×seat stratum.
