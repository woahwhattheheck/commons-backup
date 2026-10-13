# V3.1 B5 CARROT + JIT — current V5 selected-action ABI

Research-only recovery of the **submitted V3.1** B5 pair under the single V5 policy-family root. This is not a V4 thaw and does not modify the production runtime, `TITAN-CONFIG.json`, release pointers, or Kaggle submission.

## Historical authorities

Submitted V3.1 source is `a90d888f03987ef0b35cfd20ec3519c6144db08a`.

- `candidates/v3/overlay/b5_fertilize.py`: Git blob `2a9d606835b0d04d832a4737dcb381ad3fbef1ae`, source SHA256 `f2d03ab19e1a233566cfc9076bd8b9843c7f8d611703578218bd73c1af0f626f`.
- `candidates/v3/overlay/jit_pass_fertilize.py`: Git blob `6ef7ddcd9590e3cb3f55ceb708b8026235d59410`, source SHA256 `5ad6340bf31dab13aaba82bfe0b51e6cde18222155013be1e0e080f0a26242b2`.

The submitted R04 wrapper applied **CARROT first, then JIT**. `b5_current.py` preserves those decision rules and order. `b5_current_safe.B5CurrentABI` is the public current-ABI surface; it adds only the worker-cardinality and route-edge preconditions that R04 tapes guaranteed implicitly.

## Current seam

The adapter never calls a producer or chooses a route. The caller supplies:

- the current public observation;
- the already-selected current action;
- for JIT only, the authenticated next authored action and its exact step.

JIT is enabled only when `next_authored_step == observation.step + 1` and the next authored action has the exact represented current worker cardinality. This replaces the historical `tape[step + 1]` lookup without guessing from current policy output.

Both feature bits default **false** and require exact `bool`. CARROT may still execute if JIT's next-route envelope is missing/malformed because CARROT never depended on future tape state. A malformed selected-worker envelope makes the whole pair identity.

### CARROT

Changes only literal `PASS` for a worker already standing on a CARROT, already carrying fertilizer, when integer fertilizer coverage is less than `day + 2`. It never edits market rows and refuses malformed potentially-transformable evidence atomically.

### JIT

Changes only literal `PASS` when the same worker's next authored action is same-day `WATER`, the worker is already on an uncovered yield-bearing WHEAT/CARROT/MELON plant, at least two yield units of headroom remain, and the worker already carries fertilizer. Duplicate qualifying workers on one tile are removed from the candidate set, matching the submitted donor.

## Contracts

```bash
cd revenue/kaggriculture/cloud-execution-lab/candidates/v5/research/b5-current-abi
python -B -m py_compile b5_current.py b5_current_safe.py test_b5_current.py
python -B -m unittest -v test_b5_current.py
python -O -B -m unittest -v test_b5_current.py
```

The focused suite covers exact donor custody constants, strict default-off flags, input immutability, CARROT activation/malformed evidence, exact next-step route binding, day-boundary and yield-cap JIT guards, submitted CARROT→JIT ordering, duplicate-tile JIT refusal, malformed selected cardinality, and the asymmetric rule that invalid future-route cardinality disables only JIT.

## Promotion boundary

This source is **not** production activation. The next gate is an authenticated current-route composer that binds the exact next authored action from the current controller without adding a second producer, followed by matched both-seat current-V5 OFF vs CARROT vs CARROT+JIT economics. Historical V3.1 evidence is motivation, not current promotion authority.
