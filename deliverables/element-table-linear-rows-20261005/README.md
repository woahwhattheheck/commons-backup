# Element table: append rendered rows without copying the prefix

This source patch removes repeated copying of the existing row accumulator in Element UI's table body. Every input row currently concatenates its rendered result into a newly allocated copy of all preceding rows. The repair appends that result one level into the existing accumulator.

The source is pinned to [ElemeFE/element `c345bb453bf11badb4831a6a3f600c9372b3a336`](https://github.com/ElemeFE/element/tree/c345bb453bf11badb4831a6a3f600c9372b3a336), on the upstream `dev` branch at preparation. The original `packages/table/src/table-body.js` Git blob is `4aea1e6b1bb54a3708a38fa0e01dde5284c5182f`.

## Integration

The complete files are retained at:

- `original/packages/table/src/table-body.js`: exact upstream preimage.
- `patched/packages/table/src/table-body.js`: complete repaired source.
- `table-linear-rows.patch`: the single source change, relative to the upstream repository root.
- `LICENSE`: upstream MIT license, unchanged.
- `SOURCE.json`: source pins and scope.

From a checkout containing that upstream source, apply `table-linear-rows.patch` from the repository root with `git apply /path/to/table-linear-rows.patch`. The complete postimage is also available for direct comparison. On a newer source revision, reconcile the small render-loop change with the current implementation before integration.

The upstream [contribution guide](https://github.com/ElemeFE/element/blob/c345bb453bf11badb4831a6a3f600c9372b3a336/.github/CONTRIBUTING.en-US.md) requires a fork, a PR targeting `dev`, and a successful `npm run dist` build. No fork, upstream branch, PR, build, or deployment was created by this packet.

## Preserved behavior

The existing `wrappedRowRender(row, acc.length)` call still runs once per input row, with the same accumulated length and order.

| Existing return shape | Appended result |
| --- | --- |
| One ordinary row VNode | One accumulator entry |
| Dense array of a tree's row VNodes | Each tree row in order |
| Array containing the expanded-row pair | One nested pair, retaining the grouping used to preserve the next input row's index |

The loop flattens exactly one array level. It does not recursively flatten expanded groups or use a variadic push that would pass every tree row as a function argument. The built-in return paths produce dense arrays. Cell rendering, tree traversal, row keys, selection, sorting, filtering, fixed-column copies, and tooltip behavior are unchanged.

## Static reasoning and limits

For a flat table of `n` ordinary rows, the old accumulator construction copies `0 + 1 + ... + (n - 1)` prior entries. At 1,000 rows, that is 499,500 prior-entry copies per table body, in addition to appending the new entries. The replacement appends each resulting entry once and avoids those prefix copies.

These are source-derived operation counts, not measured runtime results. They concern accumulator assembly only: Vue rendering, cell callbacks, tree traversal and other table costs remain. Tables with fixed columns can render separate main, left and right bodies, and each body uses this assembly path.

The broader [issue #6089](https://github.com/ElemeFE/element/issues/6089) requests smooth large-table scrolling and virtual/scroll loading. This change does not implement virtualization or establish that the issue is solved. Its complete 78-comment discussion includes historical IssueHunt funding notices of $20 and $5; a separate $100 comment was a conditional offer. This packet makes no award eligibility, reward approval or payment claim.

Validation is static source inspection and exact Git readback only. No JavaScript/Vue execution, browser profiling, dependency installation, upstream build, tests, workflows, or substitute runtime was performed. Upstream build and browser acceptance remain pending.
