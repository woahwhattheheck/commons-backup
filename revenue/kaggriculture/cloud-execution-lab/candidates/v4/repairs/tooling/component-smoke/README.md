# V4 isolated component smoke runner

This belongs to the one canonical `main:candidates/v4`. It is a local correctness runner, not a new V4 runtime, trusted CI gate, promotion gate, or gameplay-strength result. Run only code you trust: process isolation prevents imported-module collisions; it is **not a security sandbox**.

## Run

From the repository root (Python 3.9+; standard library only for the runner):

```sh
V4=revenue/kaggriculture/cloud-execution-lab/candidates/v4
python3 "$V4/repairs/tooling/component-smoke/run_components.py" \
  --root "$V4" \
  --include 'repairs/gameplay/e20-executable-prefix/test_*.py' \
  --bind "$V4/repairs/gameplay/e20-executable-prefix/e20_hire_guard.py" \
  --output component-results.json
```

Repeat `--include` for additional root-relative test globs. Every selector must match at least one eligible file; missing suites cannot hide behind passing selections. No selection means failure. Without selectors the runner requests both `repairs/**/test_*.py` and `research/**/test_*.py`; it does not request overlay or external package suites. Hyphenated non-package directories are supported. Donor, legacy, historical, original, raw, fixture and legacy-prefixed subdirectories are excluded, with unmatched selections remaining red.

Every test file gets fresh normal and `-O` interpreter processes. Unittest assertions remain active under optimization; plain Python `assert` statements do not, so optimized green is never a replacement for normal execution. Imported modules are not shared between files. `PYTHONPATH` and `PYTHONOPTIMIZE` are cleared; use repeatable `--pythonpath` for explicit dependency locations. Third-party test dependencies must already be installed. `-S` is propagated only when the parent explicitly disables site initialization.

Each file/mode must execute at least one test and have no failures, errors, skips, expected failures or unexpected successes. Import failures, import-time exits, missing receipts and timeouts fail closed. Timeout defaults to 120 seconds per file/mode; change it using finite positive `--timeout`. The command exits 0 only when all selected suites and provenance checks pass; otherwise 1. It never executes a module's `__main__` self-check instead of unittest discovery.

## Provenance and limits

Receipts bind the runner and test-file bytes, reject source changes between normal and optimized modes, and bind additional helper/fixture files supplied with `--bind`. This is **not automatic dependency-closure authentication**. Dependencies not explicitly bound are outside the hash claim. Bytecode writing is disabled, not arbitrary test writes or child process spawning. The output includes a bounded 32 KiB tail per file/mode, not the complete log; temporary full output is discarded. Paths in raw evidence identify the local execution fixture.

## Executed evidence

`RECEIPT.json` and the four raw evidence files record the actual execution. The runner's 18 checks pass in normal and optimized Python. Exact main E20 helper `9aaba92c` and test `b01fe1bf` passed 14 tests per mode, including the 9,604-case raw-slot matrix. Git blob identity was verified before execution; no whole-package or official-engine game claim follows.

The freshly listed S1 `repairs/gameplay/s1-fert-sweep` directory contained only manifest `f1489ef4`, marked donor-only/default-off. Its original test path returned 404. The mixed E20 plus S1 request intentionally returned exit 1 for the missing S1 selector although E20 passed. This proves missing-selector handling, not S1 validation or repository-wide absence.

Legacy E20 run 34665837414/job 103477416567 and S1 run 34665902561/job 103477606902 both stopped at the BASE_SHA ancestry guard before Python/gameplay tests. Their red status is not evidence of a current-main E20/S1 gameplay regression. The frozen workflow and guard are unchanged.

Self-test command, run inside this directory:

```sh
python3 -B -m unittest -v test_run_components
python3 -B -O -m unittest -v test_run_components
```

The archived local runs explicitly used `/usr/bin/python3 -S`. Component owners retain current-runtime composition, official-engine, end-to-end and paired-game economics gates. No gameplay source, config, default, archive, workflow, or Kaggle submission is changed by this tool.
