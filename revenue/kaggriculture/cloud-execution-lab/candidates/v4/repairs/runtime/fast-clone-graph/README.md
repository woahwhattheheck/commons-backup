# R04 fast-clone graph/order repair

**Verified helper repair preserved in canonical V4; not production activation.** The integration contract is `candidates/v4/CANONICAL.json`: `main` is the sole line, old refs are donor/evidence only, and legacy R04 materialization must not run against the current production ABI. This package adds no feature key, workflow, runtime import, default change, archive or Kaggle submission.

## Existing mechanism, narrow correction

Lineage: #12361/#12383 -> #12414/#12431 -> #12643. The exact predecessor patch is `84346b65edacbfb2e46580adace4ec407707ed5e`; the newer #12643 materializer is `f87712f704e8af3d87854ca1fa83837eb0a221a3`, read at commit `71f21e56b75cf761abf8a70c564952a08e996845`. Both were reconstructed locally and byte-verified against their Git blob IDs before tests.

Both predecessors contain the same defect: their fast path accepts shared mutable rows but splits those internal aliases instead of preserving them as `copy.deepcopy` does. It also rebuilds the dictionary in fixed farmer/hands/market order rather than preserving input insertion order.

The repair requires exact built-in scalar rows, exact string keys and unique mutable-container identities on the fast path. Shared containers and unusual shapes fall back to `deepcopy`. Copying the dictionary before replacing its lists preserves insertion order. The patch and repaired materializer contain AST-identical helpers, independently checked by `check_graph.py`.

## Execute the portable checks

From the repository root:

```sh
python3 -B revenue/kaggriculture/cloud-execution-lab/candidates/v4/repairs/runtime/fast-clone-graph/check_graph.py
python3 -O -B revenue/kaggriculture/cloud-execution-lab/candidates/v4/repairs/runtime/fast-clone-graph/check_graph.py
```

Both modes passed on Python 3.13.5: 32 focused contracts and 729 labelled row-sharing combinations against each transport, plus five native-AST-delta fixtures. Coverage includes mutation isolation, internal aliases, cycles, nested mutable fallback, subclasses, all six dictionary key orders, and rejection of unrelated native changes. The exact predecessor accepts the shared-row witness and fails graph equivalence. Patch application also passed on a fixture containing the retrieved native anchors, not on a full router checkout.

## Boundaries and pending evidence

The preserved materializer accepts only historical router blob `a3e2fe87c717d128e43c9b65bae2265f40d1d76d`. It is not connected to current production. Do not run it against the current production ABI.

`validate_production_patch.py --self-test` is portable. Its full mode is a preserved historical-worktree recipe requiring the original candidates/v3 layout, base `465f4263...`, authenticated router/tape blobs and exactly three proof paths. Do not run full mode from this preservation directory or treat it as a current-main production gate. No workflow is installed here.

The official 13 x 719 = 9,347-action tape equality/graph/performance gate, full-source materialization, current-package ABI port, hosted checks and gameplay/economics were not run in this session. A separate 10,000-action synthetic diagnostic measured approximately 3.25x median helper speedup; that is not official-tape or end-to-end performance evidence.

Durable coordination: #12431 comment `5642607316`; #12643 comment `5642671144`. Fold these repaired helper bytes into the existing fast-clone mechanism at semantic port time; do not create another V4 line or retain the alias-splitting predecessor.
