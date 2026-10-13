# TITAN V5 F50 — adversarial world search

F50 is a **held-release diagnostic** for the exact V5 WF1+C02 leader. It searches deterministic seed/seat cells for cases where the held candidate is worse than exact production20f, then reduces every regression family to one exact first-divergence reproducer.

Pinned authorities:

- candidate: `8b4b074012fe3bd731c218a4956f85ce8dadd74d5afe81a3e04c2795a2a533ee`
- control: `20f201161b14af7755146b08207593f9fa5df641d2f31e680792ea62c0e24239`
- engine authority: `bc8a54879ef02c7ea64b8b333d6a976f0ea65c4949149d01f463f23bccee653e`

The tool does not mint a candidate or touch `CURRENT`, defaults, release pointers, submission slots, or Kaggle.

## What makes a witness causal

For each exact opponent / seed / seat cell, control and candidate run in fresh processes under the existing pinned official-interpreter harness. F50 accepts a regression witness only when all of these hold:

1. both games complete the canonical 719 decisions;
2. candidate margin is lower than control margin;
3. before the first differing candidate action, canonical candidate-side public observations are identical;
4. the opponent action at that same pre-transition state is identical;
5. the first difference is therefore the candidate action itself, not timing, DQ, fallback, opponent drift, or state/custody drift.

If observations or opponent actions diverge before candidate action, if either game is incomplete, or if any pinned source/archive identity fails, the cell is **invalid** and the command exits nonzero. Invalid cells are not turned into gameplay claims.

Each accepted first divergence stores the exact public observation, control/candidate actions, action hashes, bank state, seed, seat, opponent, archive identities, engine identities, and final margin delta. Repeated cells with the same `(step, observation, control action, candidate action)` signature are reduced to one deterministic strongest reproducer.

## Run

Use a Linux fleet VM with the already-prepared pinned official engine cache and exact archives:

```bash
python revenue/kaggriculture/cloud-execution-lab/candidates/v5/adversarial-world-search/adversarial.py \
  --kg-root revenue/kaggriculture \
  --engine-dir /path/to/pinned-engine \
  --control /path/to/production20f.tar.gz \
  --candidate /path/to/titan-v5-wf1-c02-exact.tar.gz \
  --seed-start 1209130000 --seed-count 256 --seed-stride 7919 \
  --seats 0,1 --opponents apex_v7,arlene_v14 \
  --max-regressions 16 \
  --output /evidence/f50-search-001
```

`--seeds 1,2,3` can replace the deterministic range form for exact replay. Search order is stable: opponent, seed, seat. The run stops once `--max-regressions` accepted regressions have been collected; use a larger limit or another disjoint seed range for broader pressure.

Outputs:

- `run.json` — archive/engine/harness/opponent identities and execution contract;
- `rows.json` — every completed/invalid cell observed before stop;
- `report.json` — aggregate deltas plus `minimal_reproducers` grouped by causal first-divergence signature;
- `.harness-snapshot/` — authenticated execution closure used for the run;
- `opponents/` — exact prepared reference-policy runtimes.

A negative result is still useful: it bounds the searched seed/opponent/seat region. A positive regression result is **not** a release decision by itself; root owns the V5 superiority gate and submission authority.

## Tests

The committed tests are engine-free hostile contract tests for search planning, complete-pair classification, same-state causal divergence, observation/opponent drift rejection, identity traces, and deterministic witness reduction:

```bash
python -m unittest revenue/kaggriculture/cloud-execution-lab/candidates/v5/adversarial-world-search/test_adversarial.py
```
