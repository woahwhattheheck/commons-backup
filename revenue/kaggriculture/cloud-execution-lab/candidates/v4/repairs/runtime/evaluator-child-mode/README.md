# TITAN V4 evaluator child optimization-mode recovery

This is a recovery of previously completed, locally executed V4 evaluator-correctness work into the single canonical `main:candidates/v4` workspace. It is not a second evaluator, gameplay policy, config/default change, release archive, Kaggle submission, or successor V4.

## Defect

`reference/evaluator/evaluate.py` launches candidate agents in fresh Python subprocesses. The incumbent worker command used `sys.executable, -B, -u` and the deliberately minimal child environment did not set `PYTHONOPTIMIZE`. Therefore a parent evaluator started with `python -O` or `python -OO` still launched mode-0 agent workers.

Recovered direct-worker evidence observed parent modes `[0,1,2]` producing incumbent child modes `[0,0,0]`.

## Recovered repair

`SOURCE.patch` is source-bound to evaluator input Git blob `1fb6b655bb4ca1e1684be165a8ef513e2e6c2325` and expected repaired blob `6d9edcc4ec5eeee22c8a6faec6ddd208a9a2e9e7`.

It changes exactly three sites:

1. Forward parent `sys.flags.optimize` as repeated `-O` arguments when spawning each worker.
2. Report the worker's real `sys.flags.optimize` and `__debug__` in the startup message.
3. Fail closed when the ready report's strict types or values disagree with the parent, otherwise record the attested mode in existing Actor statistics.

The repaired direct-worker evidence observed child modes `[0,1,2]` for parent modes `[0,1,2]`.

## Executed evidence recovered from the original packet

The original execution receipt records:

- Python `3.13.5`.
- 35/35 focused source/worker/report-integrity checks in normal mode and 35/35 under `-O`.
- Six deliberately broken evaluator variants behaviorally rejected in each mode, with four healthy controls each.
- 12 complete official-interpreter games: one seed (`9922999`) × both seats × original/repaired evaluator × parent modes 0/1/2.
- 8,628 native-agent calls and 8,640 interpreter calls including initialization.
- Original-vs-repaired and cross-mode action traces, full-state traces, and scores identical on that declared panel.

This is checked-release regression evidence, not opponent-diverse strength, hosted Kaggle validation, current assembled-V4 parity, deadline improvement, or Python 3.11 evidence.

## Consumption

The target source on current `main` was re-read before this recovery and still had exact blob `1fb6b655bb4ca1e1684be165a8ef513e2e6c2325`, so the recovered patch preimage remained exact at publication time.

A runtime owner may consume `SOURCE.patch` directly into the current evaluator and re-run the focused checks. Do not duplicate this repair through a second evaluator or alternate V4 tree.

`RECOVERY-RECEIPT.json` preserves the recovered execution identities, hashes, limits, and explicit non-claims.
