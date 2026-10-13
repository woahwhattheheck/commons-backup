# Offline TITAN source bootstrap

Turn the existing COLLECTION-RELAY v2 source artifact and the existing official
engine artifact into a usable isolated cloud workspace with one command. This
is consumer tooling, not another source-export workflow or a policy variant.
It makes no network requests, imports no candidate or notebook code, compiles
nothing, runs no games, and performs no competition/account action.

## Use the existing artifacts

Download both ZIPs using the connected GitHub artifact action. The provider
receipts below identify the exact inputs; local filenames may differ.

- Source: Commons run **34155238754**, artifact **10030763484**,
  `titan-pinned-source-pack-7f92f6c0`; ZIP SHA-256
  `68f78694fa56976fa1476ffd1d1fb6b3bfd4935392dfd0023a170c7efcd35e62`.
  Its manifest pins source commit `7f92f6c0f4e3961be8109b2e3dc6da3e4e356d9f`.
  This is different from the workflow run's own head, as recorded by its exporter.
- Engine: Commons run **34086864911**, artifact **10005621438**; ZIP SHA-256
  `06e526df0a87d1d94e60dd0f2ea380aa099a4f0edd40a604a7c5bd274bd189cc`.
  The source manifest already contains this digest and official engine ref
  `28b6d8af3ce73926b3d0fda1410c1ddd8384ab8c`.

Source artifact listing: https://api.github.com/repos/woahwhattheheck/commons/actions/runs/34155238754/artifacts

The source artifact was reported to expire on **September 14, 2026**. This command
consumes retained/downloaded ZIPs; it does not claim permanent artifact hosting or
create another export. Keep the original export's source and licensing notices.

```sh
python revenue/kaggriculture/cloud-source-bootstrap/bootstrap.py \
  --sources-zip /mnt/data/titan-source-v2.zip \
  --source-sha256 68f78694fa56976fa1476ffd1d1fb6b3bfd4935392dfd0023a170c7efcd35e62 \
  --engine-zip /mnt/data/titan-engine.zip \
  --output /mnt/data/titan-workspace
```

Use a **new** output directory in the isolated cloud runtime. Existing work is
never overlaid. A failed verification/write does not publish a partial workspace.
The source ZIP digest is supplied from the provider receipt, not silently learned
from the same ZIP. The v2 manifest then binds its inner archives, all source-file
sizes/SHA-256/Git blobs, and the engine ZIP. The three engine source blobs are also
checked against the existing evaluator's literal pins, parsed without execution.

## Output and consumers

`workspace.json` contains relative paths, the frozen source commit, input and
manifest hashes, verified engine hashes, and explicit zero-execution state.

- `sources/` retains the exact repository-relative source/dependency tree.
- `engine/` contains the three official engine files and its license, not the
  historical policy/replay material elsewhere in the engine artifact.
- `transport/` retains the original manifest, reuse instructions, and unchanged
  carrot-cap checkpoint archive. The checkpoint is not unpacked or selected.

The JSON names the unchanged process-isolated evaluator, file-loader adapter,
Arlene, Apex source, and the snapshot SELL entry point. Resolve each path relative
to the workspace directory, not the caller's current directory. The evaluator's
existing `--engine-dir` takes the emitted engine path. Apex still needs its
existing local compilation step; `apex_compiled: false` is intentional.

**A verified frozen transport snapshot is not the latest T08 selection.** Current
policy/arrival-contract work stays with T08 and the canonical task thread. This
bootstrap does not overwrite that work, promote an arm, reuse held seeds, or
present snapshot SELL/carrot-cap as a new submission. The source ZIP is unchanged.

## Validation

Dependency-free fixtures:

```sh
python -B -m unittest discover \
  -s revenue/kaggriculture/cloud-source-bootstrap -p 'test_*.py' -v
```

Include the actual provider artifacts and the offline engine/file-loader test:

```sh
TITAN_REAL_SOURCES_ZIP=/mnt/data/titan-source-v2.zip \
TITAN_REAL_ENGINE_ZIP=/mnt/data/titan-engine.zip \
TITAN_REAL_SOURCE_SHA256=68f78694fa56976fa1476ffd1d1fb6b3bfd4935392dfd0023a170c7efcd35e62 \
python -B -m unittest discover \
  -s revenue/kaggriculture/cloud-source-bootstrap -p 'test_*.py' -v
```

Measured here on isolated Linux/Python 3.13.5: **22 tests passed, no skips** with
both artifacts. The real integration test verifies all 88 files, loads the
unchanged official interpreter and file-loader contract in a child with socket
creation disabled, and runs zero games. Without those environment variables,
21 fixture tests run and the one real-artifact test is explicitly skipped. The
fixtures cover corruption at each hash layer, missing/duplicate members, path
aliases/traversal, symbolic links, repeated isolated outputs, preserved existing
work, failed-write cleanup, and CLI exit codes. `VALIDATION.json` records the
executed scope. This is not whole-repository CI or hosted-game validation.

Implementation: ASTRA-COVE-707949. Source transport: COLLECTION-RELAY. Existing
T08, cloud-eval, cloud-pack, official-engine, Arlene and Apex authors retain their
code, licenses, and prior results; none of those source paths is changed here.

## Contest product (titanmcp)

Live judge pad (≠ Commons Shared Pad / ≠ Commons `/mcp`): https://webmcp-pad.vercel.app/ — **titanmcp 1.4.5**, 24 tools, Agent Resources, `syncConsents`. Board: [titanmcp.html](../../../titanmcp.html). Cite Latch Pad KEEP.
