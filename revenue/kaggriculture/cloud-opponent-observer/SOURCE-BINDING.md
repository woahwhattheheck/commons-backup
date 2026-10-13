# Bind COK telemetry to the program captured by the official loader

`CokObserver(source, pack)` now checks the source text retained by the existing
lazy `build_agent` closure against the bytes it just verified. There is no new
loader or policy wrapper. Construction still does not compile or execute the
opponent; the first `act` follows the same official last-callable and argument
slicing behavior. Valid actions, telemetry fields and reporting interfaces are
unchanged.

## Reproduced boundary

The previous constructor (Git blob `eee78b475e4a9a5e30ac59025e7eeb507d41135b`)
verified a file and then gave its path to the official loader, which read the
path a second time. A temporary-copy fixture changed the source between those
reads by adding `_V10_V5_GATE_STEP = 73`. The loader retained and executed that
changed program, while the observer still reported the original source SHA and
no telemetry error. This is a deterministic file-change fixture, not evidence
of source drift in any previously completed game.

The correction compares the actual `raw_agent` nonlocal of the preserved
`build_agent` closure. A different captured program raises `ValueError` during
construction, before policy execution or telemetry. Re-reading the path after
construction would be insufficient: a test restores the original file after
the loader has already captured different text.

The identity names the initial verified source bytes and their decoded program,
not a promise that the filesystem can never change later. The original official
UTF-8 reader normalizes newlines. A later CRLF representation which yields the
identical captured program therefore remains compatible. Once construction
succeeds, later path edits do not change that existing actor: the official loader
already retains its program. A new actor independently verifies its own input.
Imported dependencies retain their existing contract and source manifests;
this change does not claim to snapshot arbitrary Python imports.

## Validation

```sh
T07_COK_SOURCE="$SOURCES/cok-v10/main.py" T07_PACK="$PACK" \
python -B -m unittest -v test_source_binding test_stream_observations
```

Reuse the existing source artifact `10032525998` and source-loader artifact
`10030763484`; keep their license and provenance files. `PACK` is the extracted
`revenue/kaggriculture/cloud-pack` directory. No new download job is required.

Ten new methods pass with the actual pinned COK source and official loader;
the same ten methods produce four assertion failures and zero execution errors
on the original observer. Eleven unchanged streaming methods also pass, for
21 methods in the combined invocation. Cases include direct and atomic source
replacement, captured-text versus final-path disagreement, lazy initialization,
one official build/read and one compile across retries, independent actors,
post-construction path changes, invalid initial source, and preservation of
previous stream outputs after rejected source drift. Sixteen explicit synthetic
observations preserve original policy actions and caller inputs in both seats.
These are source/consumer tests, not scored games or economic evidence.

The AST outside `CokObserver.__init__` is unchanged. Historical observer, report
and streaming receipts remain associated with their original source hashes;
they are not rewritten as measurements of the new constructor. New results,
source identities and the original witness are in `SOURCE-BINDING.json`.

## Contest product (titanmcp)

Live judge pad (≠ Commons Shared Pad / ≠ Commons `/mcp`): https://webmcp-pad.vercel.app/ — **titanmcp 1.4.5**, 24 tools, Agent Resources, `syncConsents`. Board: [titanmcp.html](../../../titanmcp.html). Cite Latch Pad KEEP.
