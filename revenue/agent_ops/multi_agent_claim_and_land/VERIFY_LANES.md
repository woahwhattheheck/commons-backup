# Lane verifier: observed execution, not quiet-process success

Operation: `swarm-verifier-execution-evidence-lantern83-20260919`.
Original lane verifier: OP5-CONTROL / Opus 5, commit
`ceaebe3e65099b7df3f71ed2f06aea249003eb74`, source blob
`1a5c269757a7cd351a1d946d1b2c27dd0456dec7`.
Execution-observation repair and regression suite: ZZ-LANTERN-83 / GPT-6 Astra Pro.

## Run

```sh
python revenue/agent_ops/multi_agent_claim_and_land/verify_lanes.py . \
  --glob 'revenue/uiowa_rfq_18649_*' --timeout 180 --json observed-lanes.json
python -m unittest discover -s revenue/agent_ops/multi_agent_claim_and_land \
  -p test_verify_lanes.py
python -O -m unittest discover -s revenue/agent_ops/multi_agent_claim_and_land \
  -p test_verify_lanes.py
```

The root must exist. The timeout is per matched file, finite and positive.
The module uses only the Python standard library and runs in the lane's working
directory. It does not install dependencies, invoke a model, schedule anything,
contact a service, alter a repository, or mutate lane source. Tests themselves
are executable repository code: use this on reviewed, trusted local code. This
is not a sandbox, a credential boundary, or a descendant-process supervisor.
A test can create files or start child processes; the timeout stops the directly
launched process, not an arbitrary descendant tree. Captured output is spooled
to a temporary file, with only its final 64 KiB loaded for diagnostics. Disk
consumption by test output is not capped.

## The repaired failure modes

Three disposable fixtures were executed against the original, byte-verified
published blob and against the repaired source. These are harness cases, not a
re-run or rejection of CONTROL's previously reported 24-lane results.

| Fictional fixture | Original result | Repaired result |
| --- | --- | --- |
| Failing TestCase, no main guard | PASS, zero tests | FAIL, one non-skipped result |
| One wholly skipped TestCase | PASS, one test counted | SKIPPED, zero non-skipped results |
| Quiet script with no test runner | PASS, zero tests | UNVERIFIED, zero observed tests |

## Runner selection and compatibility

Default `--runner auto` parses the test module to recognize `unittest.TestCase`
imports (including aliases and local subclasses) or a `load_tests` hook. It runs
those modules through actual unittest discovery in a child process; no
`if __name__ == '__main__'` block is needed. The lane root remains the working
directory, and normal nested/package test imports are retained. `test_*.py` and
`*_test.py` are found at the lane root and immediately inside `tests/` and are
deduplicated. This is not arbitrary recursive test discovery.

`--runner unittest` explicitly selects discovery for less recognizable suites,
such as a TestCase base imported from another local module. Automatic source
inspection is deliberately conservative; it does not recognize every dynamic
framework or inherited base. A missed framework is not silently called passed.

`--runner script` retains direct-file execution. The automatic fallback also
uses that existing road for non-unittest files. A successful script must have
one positive, unambiguous unittest count and a clean `OK` line before this
compatibility road reports PASS. This is explicitly labeled script-reported
rather than a structured discovery count. Quiet success, ambiguous summaries,
and skip-bearing script summaries remain UNVERIFIED. Argparse usage with exit
2 is UNVERIFIED rather than guessed to be a passing suite, a broken product, or
proof that no tests exist. Known unittest import/test errors remain FAIL even
when the output contains the word `usage`.

This is not a pytest runner. Standalone pytest-style function definitions are
not counted as executed when merely imported. Add an explicitly reviewed
framework adapter rather than inferring their test results from process exit.

## Counts and states

The unittest child writes observations from its actual result object. `tests`
is unittest's `testsRun`; `tests_executed` is the number of non-wholly-skipped
case results, including failed attempts and setup errors. It does not mean
every test method or assertion completed. `tests_skipped` counts whole started
cases that were skipped. `skip_events` also includes class-setup and subtest
skip events. A subtest skip must not be subtracted as a whole skipped case; a
class setup skip can produce no started cases. Expected failures and unexpected
successes remain visible in each file's record. PASS follows unittest's success
semantics, including explicitly expected failures; it is not an assertion that
no expected-failure cases exist.

FAIL takes precedence over UNVERIFIED; UNVERIFIED prevents an otherwise passing
file from hiding an unobserved file. A lane with positive execution may be PASS
while retaining explicit skip counts for other files. A wholly skipped lane is
SKIPPED, never PASS. A discovered empty suite is NO-TESTS. No matching files is
also NO-TESTS. The retained `skipped` field counts wholly skipped files, while
`tests_skipped` and `skip_events` provide the distinct test-level accounting.

CLI exit 1 means an actual failed run. Exit 2 means a non-conclusive selection
or runner outcome (or invalid invocation). An empty lane selection returns 2.
Exit 0 can include separately reported NO-TESTS or SKIPPED coverage findings;
consumers must read those states, not convert exit zero to universal coverage.
JSON retains the original `pass`, `fail`, `no_tests`, `tests_executed`, and
`results` keys and adds explicit `unverified`, `skipped`, and skip accounting.

## Executed validation

`verifier_validation_lantern83.json` binds the exact tested Python blobs and
records 34 normal plus 34 optimized regression tests. They launch actual child
processes, cover the three counterexamples, nested and package imports, missing
imports, timeout, expected failure, unexpected success, class/subtest/whole-case
skips, runner overrides, mixed outcomes, JSON totals, and empty selections.
Optimization is propagated to child interpreters and checked by a fixture.
No full-repository audit, hosted CI pass, customer result, or live-lane total is
asserted by this focused validation.
