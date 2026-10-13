# One native optimizer stack: WEAVE

This package composes existing SIEVE, MEADOW, EVENTPATH and CACHELIFE sources into **one** `selected_sell_core.py`, in the existing canonical V4 performance workspace. It is an executable consumption recipe plus combined evidence, not another optimizer policy, full-runtime serializer, release branch or production installer. Existing peer implementations remain in their original directories and are not copied here.

## Exact composition and ownership

The reviewed active parent is Git blob `f23d3a8b5ee5e82029026e7f8f44eb36c143a5a3`. Apply:

1. SIEVE `5ade322bfdc916b7d3ac071ab2e3fc60fb1f0db0` first, producing `5e6be72cda2e71a1aff6c68b13a0a934b2964a36`.
2. MEADOW `6b8a32669d75f6a239c3a2b78cafa6c92402d719`, producing `aae1c0c5a508797037757e745d946cddfc83404f`.
3. EVENTPATH `f7ae150bc47058393552fd1d7600b7f5d5aaa84c`, producing `23e8f02e9f50cb569556f045edfa085c67739eaf`.
4. CACHELIFE `e48861b8fe186ded0337aa66ba68833b760708b3`, explicitly authenticating that preceding blob.

Final Git blob: `16dde00627effa5d0ae4d73a8e05a295e9534e1f`. Final SHA256: `6bd91f5b8132df2c10b127f69e3dc43c4b9b9fbf32b38860ce1c7517d1575256`.

SIEVE's whole-module input pin means it cannot be applied after a peer edit. MEADOW and EVENTPATH commute byte-for-byte in the tested composition; their original methods and all unrelated top-level source remain authenticated. CACHELIFE wraps the final optimizer without changing its existing statements. The recipe authenticates every dependency before importing any and compiles the authenticated bytes. Source drift, missing/modified components, reapplication and output overwrite fail closed. No new configuration key or default is introduced.

CANOPY yielded its later overlapping composer claim and owns the complementary `check_optimizer_stack_lifetime.py` and `OPTIMIZER-STACK-LIFETIME.json` in this same directory. Its proof is separate from this session's executed checks. The source components retain their original owners. FUNDING-PERF, PORTAGE and REGRET are acknowledged complementary future inputs, **not included** in this four-source certificate. Do not multiply their independent speedups or install multiple overlapping cleanup wrappers.

## Executed combined evidence

`check_optimizer_stack.py`: **13/13 normal and 13/13 under `python -O`**, zero errors/skips. Each mode executes 324 complete optimizer-result and capacity-callback-order pairs, 1,604 score comparisons, 1,920 receipt comparisons, eight missing/modified dependency controls and seven actual CLI refusal controls. Physical infeasibility, all three existing E18 rules, floors, integer-domain fallback, terminal horizons, score-context changes, source preservation and order constraints are covered. These counts are component cases, not games.

`run_optimizer_stack_games.py`: **32 complete games** across normal and optimized Python: two seeds, both seats, official starter and PASS opponents, baseline and combined arms. Each mode compares 5,752 complete returned-action/interpreter-state frames and observes 6,790 actual native optimizer calls per arm. No fallback/error callbacks occurred. Complete optimizer result telemetry and horizon counts also match; normal/optimized non-timing evidence agrees. Surplus authored hand rows are passed unchanged to the actual engine, not truncated to satisfy the old evaluator assertion. Every agent receives only its own observation. The runner is a local official-interpreter evaluator, not the hosted Kaggle runner.

The parent is **existing artifact 10175943272**, ZIP SHA256 `3a3b74936d238bf884f89a1b279f42676cda35c590f131a6a3548de52d61b4e8`. Its SOURCE SHA256 is `e87d70dd3bcf5aea1e929f1a5dbdc86f3cc33d8a0b3492986f2970fc8e774be2`; all 109 runtime members are checked before each game. Only the active core is replaced in memory, before the original native caller imports it. The manifest, default config, entrypoint and other 108 members remain unchanged. This is checked-archive native parity, **not arbitrary current-HEAD/full-V4 parity**. The active parent source was independently read back on main as f23d during this work.

`benchmark_optimizer_stack.py`: 17 alternating samples per arm/cohort, 12 optimizer calls/sample, exact result equality checked outside every timer. Normal / optimized median ratios: short horizons **1.184x / 1.144x**, long **1.729x / 1.779x**, mixed **1.505x / 1.475x**. This is one fixed local optimizer workload, not a general whole-agent speedup or financial/leaderboard estimate. Garbage collection is enabled; explicit pre-batch collection is untimed. Game timing is observational, sequential and instrumented; do not present it as a randomized latency trial.

### Limits that must survive integration

The two opponents are deliberately simple controls, not a competition-strength panel. Exact game outcomes are unchanged; no playing-strength gain is claimed. Full-runtime interactions with later V4 components still belong to the existing serializer. Original broader package-suite failures were not reclassified as green by these targeted checks.

CANOPY's independent characterization found a **pre-existing construction-interruption cycle**: interruption before MarketPath's third cache installation leaves one bound-single/self cycle in both the parent and four-source stack while GC is disabled; ordinary collection releases it. CACHELIFE's finally begins after construction. Post-construction score/capacity cleanup and the constructor boundary are different contracts. This package does not claim universal interruption-leak freedom and does not silently rewrite the peer's constructor.

## Reproduce offline from the existing artifact

Set `RUNTIME` to the extracted `final-pressure-runtime` directory of artifact 10175943272. Set `PERF` to this directory in the canonical main checkout. No downloads, Actions dispatches, new Kaggle submissions or paid services are needed once those inputs are present. Use fresh output names/directories.

```sh
python "$PERF/compose_optimizer_stack.py" "$RUNTIME/selected_sell_core.py" /tmp/weave-selected.py
python "$PERF/check_optimizer_stack.py" --runtime-root "$RUNTIME" --json /tmp/weave-normal.json
python -O "$PERF/check_optimizer_stack.py" --runtime-root "$RUNTIME" --json /tmp/weave-optimized.json
python "$PERF/benchmark_optimizer_stack.py" --runtime-root "$RUNTIME" --json /tmp/weave-timing-normal.json
python -O "$PERF/benchmark_optimizer_stack.py" --runtime-root "$RUNTIME" --json /tmp/weave-timing-optimized.json
for seed in 9922999 9600912; do
  python "$PERF/run_optimizer_stack_games.py" --runtime-root "$RUNTIME" --panel-dir "/tmp/weave-normal-$seed" --panel-seeds "$seed"
  python -O "$PERF/run_optimizer_stack_games.py" --runtime-root "$RUNTIME" --panel-dir "/tmp/weave-optimized-$seed" --panel-seeds "$seed"
done
```

A panel writes `PANEL.json` only after every requested pair passes full comparisons. A killed/error process may leave partial per-game outputs; these are not completed panels and were not counted in this receipt. Re-run into a new directory rather than accepting partial results. The JSON execution companion contains complete component logs, the common identical per-cell results, completed-panel file commitments and every benchmark timing sample. Stage provenance is in the main receipt. The runner recreates detailed per-frame hashes; the receipt retains their full-game commitments without bloating the repository with repeated frame arrays.

Consume this single recipe in the existing V4 staging process. Never replace an independently changed core with the old parent to make its pin pass. Any semantic extension must be explicitly composed/reviewed and rerun through combined contracts. No production/default/archive/Actions-workflow/Kaggle change was made by this delivery.
