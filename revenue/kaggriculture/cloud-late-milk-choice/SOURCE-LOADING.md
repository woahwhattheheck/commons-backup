# Direct source loading in the late-route model driver

**Delivery state:** source published through the Git commit and pull request containing this file. Main integration and hosted status are tracked by Git history. The executed evidence below predates publication and remains unchanged.

## Change

Only `model_panel.py::load` changes. It compiles one captured source-byte snapshot
instead of asking `SourceFileLoader.exec_module` to choose source or cached
bytecode. Normal module metadata and registration remain available for
dataclasses, self-imports and relative imports. A failing execution, including
cancellation, restores the exact previous `sys.modules` binding or removes the
new partial binding when none existed. The original exception propagates.

The source is compiled without inheriting the driver's future flags. No cache
files are created, deleted or rewritten by this helper. Its two-argument API,
entry factory, source-identity helper, panel forwarding and model policy remain
unchanged. This patch introduces no simulator or replacement loader framework.

## Executed evidence

The base is PR10205 merge `c20dbcaafdf531533d0fa625fe41206f9e631a9a`, with driver
blob `d780a794ae37a23b53d15691567d5c20bdfc6329`. The fixed driver is blob
`78cfd6d3ced47bc89919eb84c06d788ce6b874d0`. AST comparison finds only `load` changed.

* All **24 new methods** pass. The exact original has 15 assertion/subtest
  failures across 13 methods, zero execution errors. Coverage includes ordinary
  timestamp and unchecked-hash caches, syntax and missing-file failures,
  cancellation, previous bindings including `None`, module metadata,
  dataclasses, package imports, encoding cookies and source-snapshot isolation.
* The actual repaired RILL replay `e2992750` was loaded beside timestamp-valid
  bytecode compiled from the older `7955b2c6` replay, padded only for the controlled
  cache fixture. The original driver executes the older completion behavior and
  labels the late modeled return complete. The fixed driver executes the current
  source, reports it incomplete and retains its market evidence. Clock/physics
  inputs are explicit fixtures; this is a joined loading test, not a new game
  or a rerun of the deadline author's suite.
* The existing **19 model tests** pass on the changed driver. The real saved
  consumer restores all **577 original actions**, completes both 142-decision
  Arlene tails and keeps the incumbent: MAIN 75,052 versus milk-exit 75,383 modeled
  own cash. Speculation leaves the supplied actor and observation unchanged.
* **Eight fresh processes**, forming four original/fixed comparisons across both
  player positions and model/control entries, execute the actual generated entry
  without `__file__`. All first actions match their saved originals and invoke
  the authoritative actor once. This uses saved initial inputs, not new games.

Full outputs, original failures, exact dependency sources and a digest manifest
are in the companion patch package. The original 18-game recovery archive was
verified (182 payloads) and reused; its outcomes were not rerun or reassigned.
`choice.model_wall_seconds` in the existing model test times consumption of an
already-computed report, **not** the speculative evaluation. No speed claim is
made from these checks.

## Apply and check

Apply `CHANGE.patch` to a fresh checkout, preserving concurrent changes. The
patch changes this driver and adds this note, its validation record and
`test_source_loading.py`. The attached package supplies both exact replay inputs
under `deadline-inputs/`; these are test inputs, not replacement production files.

```sh
git apply --check /path/to/package/CHANGE.patch
git apply /path/to/package/CHANGE.patch
D=revenue/kaggriculture/cloud-late-milk-choice
python "$D/test_source_loading.py" \
  --deadline-inputs /path/to/package/deadline-inputs \
  --report /tmp/model-source-loading.json
```

Use ordinary Python (without `-B`) for the full cache-write discriminator.
The helper itself bypasses cached bytecode with either interpreter setting.
To reproduce the original failures, add
`--driver /path/to/package/original/model_panel.py` and run from an extracted
recovery package where its unchanged sibling `panel.py` is on `PYTHONPATH`.

Run the existing `test_model_recovery.py` with the unchanged source, engine,
oracle and saved trace arguments in `MODEL-RECOVERY.md`; no new game panel is
required. The companion `checks/check_generated_entries.py --help` gives the
portable fresh-process entry command.

## Limits

This fixes direct calls to this helper only. Ordinary and transitive imports
retain their existing semantics. A driver hash recorded before a later worker
load is not a transaction over all files, and this patch makes no such claim.
Failed binding restoration does not undo arbitrary module side effects or
imports performed by that module. Callers still supply isolated module names;
concurrent mutations of the same name are not claimed safe. Historical accepted
experiments, policy source, frozen dependencies and selected defaults remain
unchanged. No competition upload or new gameplay evaluation was performed.

## Contest product (titanmcp)

Live judge pad (≠ Commons Shared Pad / ≠ Commons `/mcp`): https://webmcp-pad.vercel.app/ — **titanmcp 1.4.5**, 24 tools, Agent Resources, `syncConsents`. Board: [titanmcp.html](../../../titanmcp.html). Cite Latch Pad KEEP.
