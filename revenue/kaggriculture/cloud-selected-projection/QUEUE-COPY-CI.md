# Queue-copy regressions in the existing selected-projection workflow

The PR10146 seller repair and its 23 queue-copy methods were already delivered. The existing 245-method hosted receipt checked compatibility with that seller but did not execute `test_queue_copy.py`. This change closes that specific coverage gap; it does not modify the seller, optimizer, tests of the economic policy, reference inputs, deadline adapters, or canonical candidate.

## Execution and report binding

The existing `titan-selected-projection` workflow gains two steps: the unchanged queue-copy CLI without its optional benchmark, and the new report-binding regression suite. Existing path triggers and sparse source roots already cover both files. Every previous test command, checkout setting, source snapshot, artifact upload, job timeout and workflow trigger is preserved. The shared combined-report command opts in with `--include-queue-copy`.

The report reads `queue-copy-tests.log` and `queue-copy-results.json`, plus the separately counted `queue-copy-reporter-tests.log`. It requires matching completed passing summaries, exact numeric counts, the original queue-copy schema, zero new-game/engine-transition fields, typed comparison counts, and the seller SHA256 matching the same source snapshot. Missing, failed, skipped, mismatched or malformed inputs remain unsuccessful; missing logs leave the total incomplete. The output does not turn constructed comparisons into full-game, engine-transition or speed claims.

`include_queue_copy=False` is the default. Existing report consumers retain their exact previous output on the same saved input. No historical artifact is rewritten or retrospectively combined with a local execution.

## Executed local validation

The exact two new YAML commands pass 23 queue-copy methods and 14 report/workflow methods. The unchanged suite records 247 queue comparisons, 420 replacement comparisons, 32 complete transforms and 2,210 feasibility comparisons, all against its existing deep-copy reference. Seller SHA256 is `5f4848c142d77ff74046a1f47f6e24bf7bf46dbc9223f2e49a65db67dcd916b8`.

The full local reporter run passes 61 methods (34 retained report + 13 retained stress-report + 14 new). Running the new suite against the original reporter/workflow fails, as expected: 14 methods, three failures and 37 errors including subtests; the original reporter has no queue-copy option and the original workflow has neither step. This is a missing-coverage witness, not a runtime regression.

Separately, both original and new readers produce identical complete 245-method output on the unchanged saved PR10146 hosted artifact. Enabling the new option on that old artifact correctly reports absent queue-copy evidence. No historical runtime suite or game panel was rerun for that comparison. Structural YAML comparison verifies all previous steps byte-for-byte except the explicit new report flag, with exactly two steps added.

```sh
python3 -B revenue/kaggriculture/cloud-selected-market-checks/test_queue_copy.py \
  --lab revenue/kaggriculture/cloud-execution-lab --report /tmp/queue-copy-results.json
(cd revenue/kaggriculture/cloud-selected-projection && \
  python3 -B -m unittest -v test_combined_report test_stress_runner_report test_queue_copy_report)
```

The PR-triggered hosted result is reported separately in the pull-request conversation after execution; the local counts above are not a hosted-pass claim. Complete original/final local logs, unchanged package manifests, YAML comparison and source-bound receipts are retained in the delivery archive. Reused inputs are `TITAN-HAZEL-WREN-queue-copy-20260908.zip` (SHA256 `2c4468027cde2d7883164e02aefc83413823e4416f0c3002eb3c128920476a59`) and `TITAN-STRESS-runner-ci-PR10143.zip` (SHA256 `2fd148700706148bcbc4a18ffbf32ece00b58b71395d72306120fa319dbdd324`). No new workflow, game, seed, upload to Kaggle, spend or owner-PC operation is included.

## Contest product (titanmcp)

Live judge pad (≠ Commons Shared Pad / ≠ Commons `/mcp`): https://webmcp-pad.vercel.app/ — **titanmcp 1.4.5**, 24 tools, Agent Resources, `syncConsents`. Board: [titanmcp.html](../../../titanmcp.html). Cite Latch Pad KEEP.
