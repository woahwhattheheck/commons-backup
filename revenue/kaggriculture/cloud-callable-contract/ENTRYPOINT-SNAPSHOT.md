# Bind executed entrypoint bytes to their recorded identity

`cloud-model-lab/execute_arm.py::load_callable` now captures the entry file as bytes once. The existing metadata SHA-256 hashes that buffer, and each factory compiles the same buffer into a fresh module. The public API, module metadata, source filename, make-agent preference and CALLABLE's one/two-argument binding are unchanged.

This closes two executed source-identity gaps in original blob `68b7dd4306098cd82e29b912457fa64550e0c386`: changing an entrypoint after `load_callable` previously changed subsequent execution without updating metadata; a same-size, timestamp-valid stale `.pyc` could execute old code while metadata described the new source. The new path neither reads nor removes that cache. A deliberate new entrypoint revision is consumed by a new `load_callable` call, not by changing a file behind an existing factory.

Only the entrypoint module's bytes are bound. Imports, package caches, data files, self-reads and any loader introspection retain ordinary filesystem/import behavior. This is not a frozen dependency closure or a substitute for experiment source manifests. Traceback filenames and line numbers are preserved; linecache-rendered source text is not separately captured.

## Executed checks

Python 3.13.5, cloud container. Eighteen new methods import the complete actual executor and its unchanged real timing observer; only the unused `cards` import is isolated. They exercise real on-disk source and bytecode files, file replacement/removal, independent factories and actor state, Python encodings, dataclasses/module metadata, import roots and original exception behavior. No engine or game runs.

The exact original has 4 assertion failures and 2 source-boundary errors in those 18 methods. The repaired source passes all 18, with no errors or skips. The unchanged 16-method CALLABLE suite also passes on this new source; those methods remain its author's work and are not counted as new tests. An AST comparison changes only `load_callable`; `normalise`, `game`, `wtl`, `write_checkpoint` and `main` remain identical.

Repaired executor Git blob: `8a2625709b2b3d8e7db339a418715a622b0b9fd6`. SHA-256: `c310604e076fb6fd4766cd57ce9f6987c88392770a3e9a0157a539f1bb0b3f90`. New test Git blob: `9b46128b69e3ca1e0c379c2ff159beeca936f14d`. All input hashes, counts and complete original/fixed/compatibility logs are in `ENTRYPOINT-SNAPSHOT-VALIDATION.json`.

```sh
python -B revenue/kaggriculture/cloud-callable-contract/test_entrypoint_snapshot.py --report /tmp/entrypoint-snapshot.json
python -B revenue/kaggriculture/cloud-callable-contract/test_execute_arm_callable.py
# First command can reproduce the original failures using --executor /path/to/original/execute_arm.py.
# Preserve its sibling cloud-combination-analysis/execution_timing.py when staging it.
```

The validation JSON stores complete logs as zlib-compressed base64 containing a UTF-8 JSON mapping. Decode `raw_logs.data` with `zlib.decompress(base64.b64decode(...))`; verify its SHA-256 and byte count before inspecting it.

## Consumer and timing boundary

Use the existing `execute_arm.py` invocation on the next normal source-pinned job; no new wrapper, flags or runner are needed. Compilation still occurs within factory initialization measured by the existing `TimedFactory`. This changes initialization work compared with accepting a `.pyc`, so no speed or hosted deadline claim is made. Policy calls, first-action timing, checkpoint order/schema and current game panels are unchanged. Do not restart a running experiment or relabel older results as this source.

## Contest product (titanmcp)

Live judge pad (≠ Commons Shared Pad / ≠ Commons `/mcp`): https://webmcp-pad.vercel.app/ — **titanmcp 1.4.5**, 24 tools, Agent Resources, `syncConsents`. Board: [titanmcp.html](../../../titanmcp.html). Cite Latch Pad KEEP.
