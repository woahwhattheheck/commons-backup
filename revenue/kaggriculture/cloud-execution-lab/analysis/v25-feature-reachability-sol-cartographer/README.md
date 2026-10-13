# TITAN V2.5 exact feature reachability / leave-one-out

**Lane:** `TITAN-V3-V25-FEATURE-REACHABILITY-BISECT-20260910-01`  
**Owner alias:** `SOL-CARTOGRAPHER`  
**Scope:** evidence only; no gameplay, canonical package, pointer, archive, or Kaggle mutation.

The current package enables eight additive flags at once:

- `seed`
- `funding`
- `redundant_hire`
- `market_pressure`
- `operating_stock`
- `crop_release`
- `idle_fertilizer`
- `early_capital`

Historical component panels do not identify which mechanisms are still behaviorally reachable after composition, which are shadowed in the tested cells, or whether disabling one improves the exact combined package. This lane closes that evidence gap without changing the agent.

## Exact object under test

The workflow binds the committed dispatch archive, not the mutable source-tree story:

- archive SHA-256: `17f536087b3a6baf4ae1222a051285766a3ea8c2ca5af6edc190d4f527e12b86`
- archive bytes: `427870`
- runtime files excluding root `SOURCE.json`: `109`
- internal `SOURCE.json` SHA-256: `1feec5a68ffde28ab7b5c7d2c92a34aa66ff5705b7d88182ef6af98df8bb5083`
- official interpreter commit: `28b6d8af3ce73926b3d0fda1410c1ddd8384ab8c`
- dependency: `kaggle-environments==1.32.7`

The runner verifies the external archive receipt, archive bytes, internal source receipt, member count, evaluator, loader, and engine blobs before gameplay. A source-tree/package pointer mismatch cannot silently redirect the experiment.

## Method

1. Safely extract the exact archive, rejecting traversal, duplicate names, links, devices, and FIFOs.
2. AST-scan active packaged Python sources for each config flag while excluding checks, tests, and historical fixtures. A `Features` declaration alone is insufficient: the run fails before games unless all eight enabled flags also have a runtime attribute or mapping access.
3. Materialize one all-enabled control plus eight variants, each changing exactly one boolean from `true` to `false`; every other file and setting remains byte-identical.
4. Play the same development opponent/seed in both candidate seats with fresh process-isolated agents under the pinned official interpreter.
5. Replay the first all-enabled control and require identical terminal scores and trace digest.
6. Compare each disabled arm to the all-enabled control by terminal margin, own score, rival score, and whole-game trace digest.

Default panel: exact packaged public Arlene, seed `2609099501`, both seats: **18 matrix games + 1 deterministic replay**. Before the first game, the runner derives a hard callback upper bound from official `episodeSteps`; the workflow rejects a plan above **45,000 total agent calls** and also checks the observed count after every game.

## Classification

- `panel_inert`: disabling the feature changed no whole-game trace in the matched cells. This is a shadow/unreached candidate, not proof of global inertness.
- `investigate_disable`: every matched disabled-minus-enabled margin delta is nonnegative and at least one is positive.
- `retain_enabled`: every matched delta is nonpositive and at least one is negative.
- `mixed_or_neutral`: the cells disagree or all margin deltas are zero despite trace divergence.

These are development-panel routing signals only. They are not held evidence, hosted-score estimates, automatic default changes, or promotion authority.

## Local contracts

```bash
cd revenue/kaggriculture/cloud-execution-lab/analysis/v25-feature-reachability-sol-cartographer
python -m unittest -v test_feature_reachability.py
python -m py_compile feature_reachability.py run_feature_reachability.py test_feature_reachability.py
```
