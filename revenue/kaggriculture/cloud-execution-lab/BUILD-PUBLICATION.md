# Complete-file publication for the current TITAN build

`build_integrated.py` keeps the same source map, renderer, archive format,
configuration, receipt schema and `--check`. Successful output bytes do not
change. Only publication I/O changes; this patch does not rebuild or advance the
current submission package.

Every output is first written to an exclusively created, same-directory stage
file. Short writes are completed; no-progress writes fail. All stages are flushed
and file-fsynced before any published path is replaced. Existing output modes
are retained. The previous archive is promoted to its hash-named historical path
before the new archive, manifest and finally the current receipt. An already
identical historical object is reused without rewriting it; differing bytes at
the same hash-named path still stop publication.

## Executed evidence

The 21-method filesystem suite passes. Exact current original builder
`30a2b456e347e5f470cda5fc30ab323168957172` fails 16 methods / 18 assertion
records, with zero execution errors. Tests use a controlled source tree, the real
source mapper, renderer, gzip/tar encoder, manifest builder and filesystem. No
policy or engine is run. The successful original/patched fixture archive is
byte-identical (58 source members, 4,952 bytes).

A real child process exits with code 73 during source-manifest staging; all three
previous published files remain exact. Partial writes, write/open/fsync failures,
and KeyboardInterrupt retain the previous bundle before promotion. The original
exception is preserved. A rename failure between promotions leaves only complete
individual files, retains the previous receipt and historical archive, and is
rejected by the existing `--check`; the next normal build repairs that mismatch.

Separate fresh-process no-argument build and `--check` commands return the same
receipt, and `--check` changes zero files. Source mapping, rendering and check
function ASTs match the current original exactly. This includes the current
route-recovery test member added while the publication repair was in progress.

```sh
python3 -B revenue/kaggriculture/cloud-execution-lab/test_build_publication.py \
  --report /tmp/build-publication-results.json
```

`--builder /path/to/build_integrated.py` selects an exact source for a differential
check. The compact original/fixed results and all source identities are in
`build-publication-validation.json`. Full sources and logs are retained in the
BROOK publication evidence package in Bryce's Library.

## Boundaries

This is atomic replacement of each file, **not a transaction across files**.
A process stop between replacements can expose a mixed generation; the receipt
is last and `--check` rejects such a state. A hard exit can leave unreferenced dot
stage files. Normal error cleanup touches only this invocation's known stages;
no sweep deletes another writer's files. There is no cross-process writer lock
or claimed power-loss durability. The existing single release owner remains the
writer. Historical archives, runtime decisions, deadlines, games and upload
ownership are unchanged.

## Contest product (titanmcp)

Live judge pad (≠ Commons Shared Pad / ≠ Commons `/mcp`): https://webmcp-pad.vercel.app/ — **titanmcp 1.4.5**, 24 tools, Agent Resources, `syncConsents`. Board: [titanmcp.html](../../../titanmcp.html). Cite Latch Pad KEEP.
