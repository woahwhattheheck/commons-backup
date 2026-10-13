# LOOMRADAR composition-intake census

`composition_intake.py` is a **read-only queue builder for the existing ASTRA-LOOM composition graph**. It closes a control-plane visibility gap: `INTEGRATION.json` can contain landed, tested, default-OFF repair packages that are not represented in `COMPOSITION.json`, while the graph's own strict discovery intentionally covers only explicitly enumerated patterns.

The census does not compose code. It never adds graph components, invents input/output identities, infers ordering, flips a feature, materializes a package, changes production, rebuilds an archive, or authorizes promotion. Existing mechanism owners keep source/economic custody; LOOM/native-assembler owners decide whether any queued package can become a real graph edge.

For each `INTEGRATION.json` row with an explicit `repair_path`, rows sharing a package are grouped and the package is classified as:

- `graph_covered`: a matching graph component is already `compose`;
- `explicitly_blocked`: the graph already records the package as `blocked`;
- `evidence_only`: the graph deliberately excludes the package from executable composition;
- `unregistered_transform_candidate`: no graph component covers the package, but the package contains a conservative source-transform filename such as `compose*.py`, `materialize*.py`, `port_current*.py`, `build_native*.py`, or `rebase_current*.py`;
- `source_only_no_transform`: no registered graph edge and no conservative transform entrypoint is visible.

Rows without `repair_path` are reported as `unroutable_rows`; the tool refuses to guess a package from prose, lane names, blobs, or Slack history. Unsafe/missing/symlinked package paths, duplicate lane IDs, malformed graph components, duplicate JSON keys, non-finite JSON, and wrong ledger schemas fail closed.

A broad graph package does not silently cover every descendant package. A narrower ledger repair counts as covered by a broad graph component only when that graph component explicitly declares an entrypoint inside the exact repair package.

## Run

From `candidates/v4`:

```sh
python repairs/tooling/composition-graph/composition_intake.py --json
python -m unittest repairs/tooling/composition-graph/test_composition_intake.py
python -O -m unittest repairs/tooling/composition-graph/test_composition_intake.py
```

The machine `queue` contains only `unregistered_transform_candidate` packages and labels every row `LOOM_REVIEW_REQUIRED`. Queue membership is a request for graph-owner review, **not** evidence that a transform is correct, composable, active, or economically beneficial.
