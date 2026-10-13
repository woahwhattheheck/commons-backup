# Recorded-input source binding

`recorded_inputs.load()` compiles one captured byte string instead of asking the
standard source loader to select between source and a timestamp-valid `.pyc`.
The recovery CLI takes its evaluator and tracer hashes from those captured bytes,
not from a second file read after execution. Source encoding declarations and
ordinary module metadata remain supported. Failed execution restores the prior
`sys.modules` binding, including `SystemExit` and `KeyboardInterrupt`, and then
propagates the original exception.

The original helper at Git blob `5d6160082cccecf2d96b0f2199cb53a7073f1127`
reproduces the stale-cache case: same-size, same-timestamp source says NEW while
the imported module executes OLD. A separate real-file fixture rewrites the file
during import and demonstrates why the receipt must identify the captured bytes.
These constructed witnesses do not establish stale execution in any historical
TITAN measurement. Original WIDEFIELD recovery, its archive, and FINCH's subsequent
719-action correspondence remain unchanged.

## Scope and measured result

Eighteen new focused methods pass with zero errors or skips. The same suite on
the exact original source has 16 assertion/subtest failures and zero errors.
Tests use real local files, actual bytecode compilation, normal module and
dataclass behavior, and the existing evaluator/tracer imports. One CLI receipt
fixture substitutes only recovery with an empty synthetic result; it does not
claim an engine transition or trajectory reconstruction.

AST comparison preserves `canonical`, `validate_game`, `recover_inputs`,
`recover_record`, and `atomic_write`. Only `load` and the evaluator/tracer hash
expressions in `main` change. There are no policy calls, engine calls, new games,
new seeds, additional replay drivers, or profiler changes in this validation.

Captured-byte identity applies only to the two modules explicitly loaded by this
helper. Their imported dependencies, the nested offline engine loader, resources
read by module code, and the adapter's own on-disk hash are not snapshots. The
existing engine source validation remains separate. This is not a complete
hermetic-execution or concurrent-module-loading guarantee.

## Reproduction

From the repository root:

```sh
python3 -B revenue/kaggriculture/cloud-trace-inputs/test_source_loading.py \
  --report /tmp/trace-source-loading.json
```

The suite locates the existing sibling evaluator/tracer files. A detached source
layout may instead provide each using `--actual-source PATH` twice. Missing real
dependencies cause one explicitly reported skip, not an all-18 success. The
`--module PATH` option permits the same tests against the original source.

Native evidence is retained in Library as
`TITAN-TRACE-source-loading-20260908.zip`: exact baseline and repaired code,
tests, original stale-cache witness, both complete test logs/results, unchanged
function comparison, and source hashes. This is a focused evidence bundle, not a
new runtime/source export. `SOURCE-LOADING-RESULTS.json` records its identity.

Use the existing recovery CLI normally on the next requested record. Previously
accepted trajectories and current experiments do not need restarting.

## Contest product (titanmcp)

Live judge pad (≠ Commons Shared Pad / ≠ Commons `/mcp`): https://webmcp-pad.vercel.app/ — **titanmcp 1.4.5**, 24 tools, Agent Resources, `syncConsents`. Board: [titanmcp.html](../../../titanmcp.html). Cite Latch Pad KEEP.
