# Complete selected-projection reports

`build_combined_report.py` reads existing suite logs, JSON outputs and their
pre-execution source snapshot. It does not import a policy or run tests/games.
The workflow keeps every existing execution command and uses this module to
write `COMBINED-RESULTS.json`, including loader, empty-lot, joined-wrapper and
funded-join coverage rather than only the first three suites. The merged
COVER capture-binding, score-schedule and workflow-binding commands are also
preserved and included in the declared runtime-regression group.

## Saved-artifact use

After verifying and extracting the normal GitHub artifact:

```sh
D=revenue/kaggriculture/cloud-selected-projection
python "$D/build_combined_report.py" --directory /path/to/extracted \
  --output /tmp/combined-reconciled.json
```

The default contract is the six original/stock-projection/market/loader/
empty-lot/joined-wrapper suites. Add `--include-funded-join` for CYPRESS output,
`--include-runtime-regressions` for the three COVER-bound runtime suites and
`--include-reporter-tests` for the reporter's own regression log. The current
workflow supplies all three flags. Missing required output remains explicit;
selecting a smaller historical contract does not establish newer coverage.

The v2 report preserves `original_tests`, `projection_tests`, `market_tests`,
source/engine hashes and case fields. `total_tests` now includes EVERY declared
suite, including requested additions. `legacy_three_suite_tests` preserves the
old subtotal for readers that need that scope. Individual suite counts come
from completed logs and are compared with JSON where supplied, never assumed
from the source's method count. `observed_tests` retains available counts when
some logs are missing; `total_tests` is then null, not a fabricated zero.

Use `complete` and `successful`, not the count alone, to interpret the result.
Failed/skipped/zero-method or truncated suites, count disagreement, missing
source rows, source/engine disagreement, duplicate JSON keys and mixed funded
run identities cannot produce a successful report. The capture suite's nested
JSON result is bound to its runtime and optimizer source hashes. An unsuccessful
report is still emitted with its problems and the CLI returns 1. The workflow
preserves prior step failures and the existing always-upload behavior.

JOINT's separate three-suite ZIP reader remains unchanged. Its accepted older
37/51-method artifacts and prior `HOSTED-VALIDATION.json` are not rewritten.
This reporter binds declarations in one source snapshot, not an independent
attestation of executed instructions or a whole-repository success claim.
When adding a future suite to the workflow, add its declared log/source/JSON
contract to the reporter as well.

## Executed validation

Twenty-four self-contained parser tests pass locally:

```sh
cd revenue/kaggriculture/cloud-selected-projection
python -m unittest test_combined_report -v
```

The generated parser fixtures are synthetic, not gameplay evidence. Separately,
the actual existing artifact10034414947 from run34166821802 was downloaded and
verified against its provider SHA256
`1323e92edc15bfe7a767dc02c60ffb3c45a0254f802397cf8b820522094a49ab`.
Its original combined subtotal is 51. The new reporter consumes its unchanged
six logs and reports 79 complete methods (16+21+14+7+15+6), with matching source
and engine bindings and no problems. This is reanalysis of saved results, not
79 fresh executions.

The initial PR10032 head `4b1a86ee2f6b85094247ea94dcc8eadbf97f206d` executed
successfully in run34175497898. Its artifact10037093197 (123442 bytes, SHA256
`ff4fd2542982ba5cf04e081bf3cc74a9206d5c3ec2e430118d76b109de6111b6`)
was downloaded and verified: 117 complete passing methods across eight suites,
including the original 22 reporter methods. This is the pre-COVER-merge result,
not evidence for the additional three runtime suites. Final merged execution
is recorded separately in the PR and its artifact.

No selected-policy, optimizer, producer, engine, game panel, seed, or external
competition state changes are part of this reporting repair.

## Contest product (titanmcp)

Live judge pad (≠ Commons Shared Pad / ≠ Commons `/mcp`): https://webmcp-pad.vercel.app/ — **titanmcp 1.4.5**, 24 tools, Agent Resources, `syncConsents`. Board: [titanmcp.html](../../../titanmcp.html). Cite Latch Pad KEEP.
