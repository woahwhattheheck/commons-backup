# Native test discovery and resource lifetime

This follow-through changes only the native test harness published in PR10168.
Its seven native test methods have identical abstract syntax trees before and
after this repair. The runtime, flow model, terminal producer, engine, selected
policy, and shared workflows are unchanged.

## Reproduced boundary

Ordinary `python -B -m unittest test_joint_terminal_native -v` previously raised
`KeyError: 'TITAN_ENGINE_DIR'` while importing the test file. Merely importing a
configured file also registered substitute engine modules without restoring them.

Engine setup now occurs in `NativeJoinTests.setUpClass`, with cleanup registered
before the first dependency load. Importing the file neither needs engine
configuration nor replaces the five temporary dependency registrations. Missing
optional configuration produces a named class skip: zero executed native tests,
one skipped class, no error. The JSON report explicitly includes `skipped` and
`skip_reasons`, so this is not a seven-test validation result.

Explicitly configured missing files, invalid module code, and wrong pinned
terminal-source hashes still fail. Normal setup and failed setup restore each
previous module registration; names absent before setup are removed. Unrelated
modules imported during the test are left in place. No whole `sys.modules`
snapshot is restored by the native harness.

## Run

From any working directory:

```sh
python -B revenue/kaggriculture/cloud-market-response/test_joint_native_discovery.py
```

These eight tests need no engine artifact. Small module fixtures exercise only
resource setup and cleanup; they do not simulate markets or claim native game
coverage. The optional `TITAN_NATIVE_TEST_PATH` points at an alternate harness
for a local negative control.

For the configured native suite, retain the exact engine and producer inputs in
`JOINT-TERMINAL-NATIVE.md`:

```sh
TITAN_ENGINE_DIR="$ENGINE_DIR" \
TITAN_TERMINAL_INPUTS_PATH=revenue/kaggriculture/cloud-score-endgame/terminal_inputs.py \
TITAN_JOINT_REPORT=/tmp/joint-terminal-native.json \
python -B revenue/kaggriculture/cloud-market-response/test_joint_terminal_native.py
```

A consumer counting actual native coverage must inspect `tests`, `skipped`,
`failures`, and `errors`, not only the process exit code.

## Executed September 8, 2026

Eight new discovery/lifetime methods pass, with zero failures or errors. Seven
configured native methods separately pass with zero skips, errors, or failures.
Every original native JSON result field is identical, including all 288 full
terminal cash-pair comparisons, 303 producer cells, 12 historical transitions,
84 exact intervals, and the fixed-slot margin difference of 34. These are the
same constructed fixtures, not 288 additional independent samples.

The unconfigured original-source traceback is retained. A deliberately altered
local candidate that omits registration cleanup fails four of the eight new
methods, demonstrating that successful import alone does not satisfy the tests.
The altered candidate is not published as production or test source.

Exact delivered source identities:

| File | Git blob | SHA256 |
| --- | --- | --- |
| `test_joint_terminal_native.py` | `2ebfa044c0812cf93c8f3d30e188b751cd566292` | `8dceef69c2456b5c8a1253fcd3b81f96b137a1c7b0103900793f780f1ec14c47` |
| `test_joint_native_discovery.py` | `638159f8500e758e7fde7f0745ca644b141fa991` | `3f57bf81c5e3685d88307a37f1105c425d38672d7230160133bb6e2e9c1ca5b4` |

PR10168's original guide and receipt remain a preserved source checkpoint;
this note identifies the later harness bytes. Its four supporting hosted checks
passed on head `8697e819570acdd95dce4c3ac96659e2c44e302b`: open-door 34187501496,
source-parses 34187501456, spec-guard 34187501465, and path-manifest 34187501606.
Those checks do not establish hosted execution of these new tests. No new full
games, seeds, runtime change, canonical release, or leaderboard result is claimed.

## Contest product (titanmcp)

Live judge pad (≠ Commons Shared Pad / ≠ Commons `/mcp`): https://webmcp-pad.vercel.app/ — **titanmcp 1.4.5**, 24 tools, Agent Resources, `syncConsents`. Board: [titanmcp.html](../../../titanmcp.html). Cite Latch Pad KEEP.
