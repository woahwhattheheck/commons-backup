# ROUTEMOTION — source-bound fixed-tape motion census

This lane is **research-only and policy-inert**. It measures main-farmer motion in the canonical V4 fixed tapes under exact pinned engine, standard-configuration, tape-bank, and router sources.

It does **not** create a worker planner, alter HIRE cadence, compete with LABORFLOW, or mutate runtime/default/archive/Kaggle bytes.

## The source theorem

The pinned official engine gives actor 0 an exact position with four directional movement operations. Movement mutates `farm["farmer"]` immediately. At end of day actor 0 resets to the canonical shed-access spawn. The interpreter executes unit actions before market processing.

Two consequences must not be conflated:

1. **Individual boundary no-op.** An out-of-bounds movement is already an engine no-op and is individually equivalent to `PASS`.
2. **Open-loop closed-motion candidate.** A same-day actor-0 MOVE/PASS interval can return to its exact starting tile with no HIRE in the interval. That is useful census evidence, but it is **not rewrite authority**.

The reason case (2) is not a PASS-equivalence theorem is source-real and observable: `_initialize()` installs the same public `farms` object into both players' observations. An executed `EAST` therefore exposes the displaced farmer position at the next callback before a later `WEST` restores it. Our own observation-conditioned wrappers or the opponent may react to that intermediate public state. Replacing the complete `EAST -> WEST` loop with `PASS -> PASS` can therefore change later actions even though actor 0 eventually returns to the same tile.

`route_motion_census.py` consequently emits schema `titan.v4.route-motion-census.v3` with one rewrite authority and one replay-only candidate class:

- `individually_pass_equivalent_movement_rows`: true out-of-bounds engine no-ops only;
- `open_loop_closed_motion_candidates`: position-restoring fixed-tape groups classified `OPEN_LOOP_REPLAY_REQUIRED`;
- `open_loop_candidate_movement_rows`: the union of candidate movement rows for counting/replay targeting only.

The old `jointly_pass_equivalent_loop_movement_rows` / atomic-rewrite vocabulary is intentionally removed. Closed loops require current-native branched replay before any transformation or policy claim.

## Bound sources

At authoring time the tool pins:

- official engine Git blob `3c202c7ee921da239356789e266b694635103fc4`;
- official engine spec Git blob `b354d06b742fe48402513792253f1a5c29366b20`;
- canonical 13×719 tape bank Git blob `a43289b9cc5e34a2481fddf652762a7d92f427ef`;
- canonical R04 router Git blob `a3e2fe87c717d128e43c9b65bae2265f40d1d76d`.

The engine semantic markers include both public-farm observation assignments (`obs0.farms = farms` and `state[i].observation.farms = farms`) in addition to movement, HIRE/spawn, reset, and interpreter ordering. The spec pin binds the census to the standard `boardSize=10` and `turnsPerDay=24` contract. A changed default fails closed.

Every authority is captured exactly once into immutable bytes. Git object identity, semantic anchors, engine-spec parsing, and tape execution derive from those captured snapshots; the tool never authenticates one pathname read and then reopens it for theorem semantics.

The effective route is reconstructed exactly as the live R04 router does:

- steps `0..143`: plan 0;
- steps `144..647`: selected plan;
- steps `648..718`: plan 2.

All 13 possible selected plans are censused.

## Run

From the repository root:

```bash
V4=revenue/kaggriculture/cloud-execution-lab/candidates/v4
python -B "$V4/research/route-motion/route_motion_census.py" \
  --output /tmp/titan-v4-route-motion.json

python -B -m unittest -q \
  "$V4/research/route-motion/test_route_motion_census.py"

python -O -B -m unittest -q \
  "$V4/research/route-motion/test_route_motion_census.py"
```

The v3 output reports per route:

- total authored actor-0 movement rows;
- market callbacks containing HIRE;
- individually PASS-equivalent out-of-bounds movement no-ops;
- open-loop, position-restoring motion candidates that require replay;
- the union of movement rows participating in those candidates for census/counting only.

It also emits the exact four source Git blobs and the authenticated standard `boardSize` / `turnsPerDay` values used by the census.

## Ownership / next gate

This packet is evidence for existing route/composition owners. LABORFLOW keeps generic productive hand assignment and redundant-HIRE economics. HERDSCALE keeps animal-throughput scaling. The canonical graph/postimage runner remains the only composition sink.

If the current tapes contain boundary no-ops, those rows have engine-level PASS equivalence but still need current-native economics before promotion. If they contain closed-motion candidates, the only valid next step is **branched current-native replay with the complete candidate group changed together**, preserving the real observation/reaction loop. A positive replay witness may justify a later transform through existing composition authority; the census alone never does.

If the census returns zero useful rows/candidates, land that as useful negative evidence and do not invent a movement policy.

## Not claimed

- closed-loop PASS equivalence under observation-conditioned agents or opponents;
- closed-loop rewrite authority before current-native replay;
- hand/worker path optimality;
- opportunity incidence after all current-native runtime repairs;
- economic or competitive uplift;
- runtime activation;
- default promotion;
- archive replacement;
- Kaggle submission.
