# Execute the verified quotation source

`reached_quote_case.load_dependencies` now compiles the same captured bytes that it hashes, using the captured file name and ordinary module metadata. It no longer delegates execution to a loader that can choose a timestamp-valid or unchecked-hash bytecode cache. A failed import or cancellation restores the prior bindings of this loader's module aliases, including dependencies loaded earlier in the failed batch. Transitive imports and arbitrary import-time side effects are not snapshotted or undone.

This applies TRACE's existing captured-source loading approach (PR10204) to the saved-input quotation consumer. No shared loading framework or runtime wrapper is added. All dependency hashes, quotation and ranking functions, CLI behavior, FLOW's PR10216 completion repair, and historical results remain unchanged. Only `load_dependencies` changes; all other function/class bodies are AST-identical to the predecessor.

## Executed result

Eighteen new source-binding methods pass; the exact predecessor reader `794b56813daf89e06b76aaa8cbb291498e15c73c` produces ten assertion-failure records and no errors in the same suite. Cases cover real timestamp and unchecked-hash caches, replacement of a file after capture, module metadata/dataclasses, encoding cookies, annotation semantics, single source reads, original exception identity, cancellation, and failed-batch alias restoration.

All eighteen unchanged PR10102 consumer methods pass, including its real CLI and retained natural DELVE226 input. The full on-time report, including every dependency-source identity, remains identical: four route/scenario comparisons and 870 variable settlements. Its canonical report SHA-256 is `be3a3c4b6c5e100551e4c5a3c75987c662ac92604058edc3105d433ac2981fb8`.

The additional actual-source witness uses the real repaired FLOW and mechanics in a temporary source copy. A timestamp-valid cache is constructed from historical FLOW1070bcad padded to the repaired file's length; the exact repaired source ddbbe439 is then restored. Both readers verify the same repaired source hash. The old reader nevertheless executes the historical cache and exposes an overdue final quote as a selectable alternative. The corrected reader executes the captured repaired bytes, returns `incomplete_budget`, and makes no selection. Both the source and cache files stay byte-identical during loading. The stale-cache fixture is constructed evidence, not a claim that any accepted historical experiment executed stale code. No actor or game is run.

## Sources and reproduction

Updated reader blob: `f5f64be61dd6277e8436d930286498486ff4f2de`; SHA-256 `d3219246f67362e6b5b34e972261eb5ba15e238a0b6fadc6430091550de8868a`. FLOW stays `ddbbe439c93082ab68b2e7e8dcfe302bbee052e7`; DATE stays `5e418aeca191e71d281f669a9fdd9f4b0730617f`. Other dependency identities remain in the reader's unchanged map.

```sh
cd revenue/kaggriculture/cloud-capital-bundles
python3 -B -m unittest -v test_quote_source_binding
```

For the direct comparison, `BASELINE_ROOT` is the PR10216 source closure with reader794b5681, and `UPDATED_ROOT` is the same closure with the new reader. `PACKAGE` is the existing `osprey-reached-quote-case.zip` extraction (Library file `file_00000000d93881f5949750cf2733e3ad`, SHA-256 `6b04149783b95a12fd7418628eacc376944fe6b26b984283d3dbd37cb441d849`). It supplies the original FLOW source and retained input/scenarios, not a new simulation:

```sh
python3 -B check_quote_source_binding.py \
  --baseline-root "$BASELINE_ROOT" --updated-root "$UPDATED_ROOT" \
  --old-flow "$PACKAGE/source/cloud-capital-route-flow/dated_flow.py" \
  --input "$PACKAGE/evidence/saved-226-row.json" \
  --scenarios "$PACKAGE/evidence/scenarios.json" \
  --output /tmp/quote-source-binding.json
```

The checker saves the actual before/after outcome, source identities and hashes in a fresh report. It does not modify original evidence, run a parent, create a new scenario model, fetch a source archive, or alter the selected policy. Conditional scheduled-volume cash is not realized game cash or a physical-fill certificate. Existing peer sources retain their attribution; new checks are Apache-2.0.

## Contest product (titanmcp)

Live judge pad (≠ Commons Shared Pad / ≠ Commons `/mcp`): https://webmcp-pad.vercel.app/ — **titanmcp 1.4.5**, 24 tools, Agent Resources, `syncConsents`. Board: [titanmcp.html](../../../titanmcp.html). Cite Latch Pad KEEP.
