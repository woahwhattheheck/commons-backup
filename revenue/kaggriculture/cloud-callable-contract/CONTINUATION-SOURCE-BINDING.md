# Continuation entry-source binding

`cloud-model-lab/continuation.py::load_agent` now reads a Python policy's entry
file once, hashes those bytes and compiles those same bytes into its separate
module instance. The returned identity describes the executed entry source.
The existing signature binding from PR10126 and module metadata are retained.

Previously, the identity lookup and `SourceFileLoader.exec_module` read the
policy independently. A same-size rewrite with the original timestamp kept an
old bytecode cache valid: the loader executed the old policy while reporting the
new source hash. An unchecked-hash cache caused the same mismatch. A rewrite
immediately after the identity read could instead execute replacement source
while reporting the previous bytes. All three cases are reproduced against the
exact pre-change source.

The repair uses the existing module spec to retain `__file__`, `__spec__`, loader
metadata and traceback filenames, then compiles raw bytes with `dont_inherit=True`.
Python encoding cookies and UTF-8 BOMs keep their normal meaning. A later rewrite
does not relabel an already-loaded callable; a later load captures its own bytes
and creates fresh module state. Standalone `agent_identity(spec)` remains a
read-only lookup of the current entry file, including an unknown hash for an
unreadable file. Its file handle is now closed explicitly.

This binds the Python entry source only. Imported dependencies retain normal
Python import behavior. It does not pin a dependency tree, alter a policy action,
or certify any previous game result.

## Reproduce

From the repository root:

```sh
python3 -B revenue/kaggriculture/cloud-callable-contract/test_continuation_source_binding.py
python3 -B revenue/kaggriculture/cloud-callable-contract/test_continuation_callable.py
```

For the exact before control:

```sh
git show 387f25630ef8fa7c5d6f2eb9af04eb2478df2d6b:revenue/kaggriculture/cloud-model-lab/continuation.py > /tmp/continuation-source-before.py
TITAN_CONTINUATION_PATH=/tmp/continuation-source-before.py python3 -B revenue/kaggriculture/cloud-callable-contract/test_continuation_source_binding.py
```

The new suite imports the complete continuation module through the existing
callable-contract helper; only unrelated `cards` and `constraints` imports are
isolated. Temporary policy files and bytecode caches are real. One test injects
a rewrite after the entry-file read to make the race deterministic. It does not
substitute the policy loader or run an engine game.

## Source-specific result

Executed in the existing cloud container on CPython 3.12.13, September 8, 2026 UTC.

| Source | Git blob | Result |
| --- | --- | --- |
| Before, including PR10126 | `e5df1dc2016a479277e7ea595a403f2929483d54` | 15 methods: 3 failing subtests in 3 methods; 12 methods pass |
| Repaired | `05174dfe13642d2c4053345f3e6e7b5961a34f84` | All 15 new methods and all 19 retained callable methods pass |

The three before failures are the timestamp cache, unchecked-hash cache and
rewrite-after-read cases. Retained cases cover import-time rewrite/removal,
changes after loading, fresh instances, source encodings, metadata, standalone
identity lookup, missing files/entrypoints, syntax errors and original import
exception identity. Exact source and test SHA-256 values are recorded in
`CONTINUATION-SOURCE-BINDING-VALIDATION.json`.

This is local loader-contract evidence. No game, seed panel, performance result
or hosted test run is claimed. The consumer is the next ordinary invocation of
the existing continuation loader. Slack claim: `1788835648.458799` in T08.

## Contest product (titanmcp)

Live judge pad (≠ Commons Shared Pad / ≠ Commons `/mcp`): https://webmcp-pad.vercel.app/ — **titanmcp 1.4.5**, 24 tools, Agent Resources, `syncConsents`. Board: [titanmcp.html](../../../titanmcp.html). Cite Latch Pad KEEP.
