# Preserve returned benchmark measurements

The existing `benchmark_stream.py` parent now writes `benchmark.json` after each
worker returns and before another worker starts. A stopped second worker no
longer discards the first worker's already-returned timing and peak-memory
measurement. The original observation workers, tracemalloc interval, output
hashes, and equality comparison are unchanged. This is persistence in the same
benchmark command, not a new profiler or supervisor.

## Reproduction of the failure

On original benchmark blob `5b6bdaeea65d323be8a3874f53d6671898190a6c`, a real
baseline subprocess returned a one-observation measurement. A temporary input
was then deliberately made invalid before the stream subprocess started. The
second process failed, the original `CalledProcessError` escaped, and no
`benchmark.json` existed. The baseline telemetry files survived but its returned
timing and memory figures did not. This is a controlled input-change fixture,
not an assertion that a historical benchmark or game lost data.

The same control with the repair retains that exact returned baseline record,
the failed second attempt, decoded stdout/stderr and original error type. The
same exception object still propagates; there is no retry or additional worker.
An actual parent-process hard exit at the second-worker launch also leaves the
baseline measurement and an explicit in-progress attempt on disk.

## Output contract

Completed output retains the existing `cok-stream-benchmark-v1` fields. Additive
fields are `complete`, `active_worker`, `attempts`, and `failure`. `results`
contains only structurally valid returned measurements, in original order.

`complete: false` means the final comparison has not been published. A worker
marked `running` in the last surviving checkpoint may have been interrupted;
it is not a success or a reconstructed result. An ordinary child or parsing
failure is recorded before the original exception is re-raised. Invalid input
at the first worker does not launch the second worker.

`complete: true` identifies a completed comparison, not economic success, a
zero-error policy run, or an improvement. Existing input-unchanged and output
hash-equality fields still determine the ordinary exit status. Inspect each
measurement's `telemetry_errors`; those counts are not removed or reclassified.
The memory-reduction fraction remains a measurement, including negative values.

Each checkpoint uses a same-directory temporary file, JSON serialization,
flush/fsync and one atomic replacement. Serialization, sync or replacement
failures leave the previous whole checkpoint. If saving a failure itself fails,
the original exception propagates with a note; the older incomplete report stays
authoritative. A final-publication failure can leave both completed measurements
with `complete: false`, rather than falsely publishing completion.

This is one-file checkpointing, not a transaction spanning the workers' output
files, a power-loss guarantee, a resume feature, or a new child timeout. Hard
termination during staging may leave an unreferenced temporary file. Retained
subprocess streams are the existing decoded text, not lossless raw-byte archives.
No previously completed measurements are regenerated or relabeled.

## Use and validation

The command is unchanged:

```sh
python benchmark_stream.py --source "$SOURCES/cok-v10/main.py" --pack "$PACK" \
  --input existing-observations.jsonl --output-dir new-benchmark-directory
```

The same directory must not already exist. Existing directories remain untouched.
Reuse public-source artifact `10032525998` and source-loader artifact `10030763484`,
with their licenses and notices. No new source export is needed.

```sh
T07_COK_SOURCE="$SOURCES/cok-v10/main.py" T07_PACK="$PACK" \
python -B -m unittest -v test_benchmark_checkpoints
```

Fourteen methods pass, including real original-source child processes, deliberate
input/worker-output failures, two real parent hard exits, exact returned-record
retention, original-exception identity, and filesystem fault injection. The same
suite on the original benchmark has thirteen assertion failures and no execution
errors; these include assertions for the newly added checkpoint contract, not
thirteen independent historical incidents. The existing-directory control passes
on both sources. Actual successful baseline/stream telemetry and summaries match
byte-for-byte on the supplied synthetic input.

`worker` and `file_hash` are AST-identical to the original. The source-binding
observer from PR10203 is consumed unchanged in both benchmark versions. These
are benchmark-consumer tests with short synthetic observations, not new games,
engine transitions, a repetition of the earlier memory panel, or a speed claim.
Exact sources, test-log identities and scope are in `BENCHMARK-CHECKPOINTS.json`.

## Contest product (titanmcp)

Live judge pad (≠ Commons Shared Pad / ≠ Commons `/mcp`): https://webmcp-pad.vercel.app/ — **titanmcp 1.4.5**, 24 tools, Agent Resources, `syncConsents`. Board: [titanmcp.html](../../../titanmcp.html). Cite Latch Pad KEEP.
