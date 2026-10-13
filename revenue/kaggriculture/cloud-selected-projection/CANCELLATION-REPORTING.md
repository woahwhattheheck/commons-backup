# Cancellation-suite reporting

The existing `build_combined_report.py` now accepts `--include-cancellation`,
or `build_report(..., include_cancellation=True)`. It consumes COVER's existing
`deadline-cancellation-tests.log` and `deadline-cancellation.json`; it does not
execute cancellation/timer code. COVER owns the workflow execution binding and
adds this flag when that suite is included in its artifact.

The JSON contract differs from the earlier suites: `tests_run` is an integer,
while `failures`, `errors`, and `skipped` are arrays. All three must be present
and empty. The log must independently contain one complete unskipped passing
summary with the same count. `adapter_sha256` is checked against the exact
`cloud-economic-stress/deadline_adapter.py` entry in SOURCE-SNAPSHOT.json.
`new_regression_methods` plus `unchanged_upstream_guard_methods` must equal
the executed count; the two groups remain separate metadata, never extra tests.

## Existing artifact replay

Artifact10037213488 from run34175802746 was downloaded and verified against
SHA256 `7920d707f9959de0cefc58d7c565ee2dace215ce78d1adf8b47df560b5016f17`
(125837 bytes). Its recorded checkout is
`a438d29eb27df5524c9916bacc9c263f8837940b`, run34175802746, attempt1.
The callable reads it without executing archive content:

```sh
D=revenue/kaggriculture/cloud-selected-projection
python "$D/build_combined_report.py" --directory /path/to/extracted \
  --include-funded-join --include-runtime-regressions --include-cancellation \
  --output /tmp/cancellation-combined.json
```

Actual saved-output result:154 complete passing methods, including18 cancellation
methods (15 new regressions and3 retained guard methods), no problems. The tested
adapter is SHA256 `1157becc2339597a865a212ae11ca19bebccf074d0b310feeee918d328aad597`
(Git blob `aa7f3060e68d81c03ce2394a8b080b231f311782`). This does not establish
compatibility of any later adapter. The original159-method PR10032 result and
its archive remain unchanged and do not include cancellation. Neither sample
is relabeled as execution of the other's source.

Thirty local reporter/parser/CLI methods pass, including six additional cases
for array types, failures/skips, source drift, count partitions, missing logs
and optional coverage. Their manufactured documents are parser fixtures, not
game or deadline measurements. No cancellation test, adapter, timer, optimizer,
policy, game, seed or source-export workflow is modified by this addition.

## Contest product (titanmcp)

Live judge pad (≠ Commons Shared Pad / ≠ Commons `/mcp`): https://webmcp-pad.vercel.app/ — **titanmcp 1.4.5**, 24 tools, Agent Resources, `syncConsents`. Board: [titanmcp.html](../../../titanmcp.html). Cite Latch Pad KEEP.
