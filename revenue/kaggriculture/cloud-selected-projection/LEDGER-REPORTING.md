# Market-ledger report integration

The existing reporter accepts `--include-ledger-schedule` (or
`include_ledger_schedule=True`). It reads the completed
`ledger-schedule-tests.log` and `ledger-schedule-results.json`, binds all four
reported runtime source hashes and the three engine hashes to SOURCE-SNAPSHOT,
and checks method count, failures, errors, skipped count and case-count types.
Reported reference-method hash and case counts remain metadata, not additional
method executions or an independently reconstructed reference function.

The existing workflow's report command now includes BOTH
`--include-cancellation` and `--include-ledger-schedule`. Every execution command,
merged-event checkout, source_context field and artifact upload is unchanged
from workflow blob `c9e2e896e8bd1838738d84aa4d1865cec345a145`. There is no new
workflow or manual dispatch. COVER retains those execution/source-closure steps;
WREN retains the ledger implementation and its tests.

## Saved-output validation

Actual artifact10037458001/run34176539701 (132712 bytes) was downloaded and
verified against SHA256
`edf33a04c6c57ad44338c79d83fe16402511ed9ca6a1548628a7f1a7a650a93f`.
It executed the merged-event checkout
`94ce4a0ff79d6a99860ee29420e9b8014d2f6b35`, not merely its source branch head.
All13 logs report passing tests:206 methods in total, including cancellation18,
ledger20 and the then-current reporter30. Its original combined JSON includes
only11 selected suites/168 methods because the two report flags were absent.

The new reader consumes those unchanged outputs with all flags and reports206
complete methods, no problems and matching source/engine identities. This is
saved-output reanalysis, not another206 test executions. Cancellation is bound
to its actually executed adapter SHA256
`c3bef158763cb4f5f8b8436800f442b1acc94be2c407c5db1e740edd3a0d68f0`.
Ledger case metadata is kept separate:1218 feasibility,99 transform and4718
ordered-capacity comparisons, plus24 official market calls. These are synthetic
source-parity/native-market tests, not full-game or timing results.

Thirty-four local parser/CLI tests pass, preserving the earlier30 and adding
four ledger cases. The new cases check optional counts, runtime/engine drift,
log/JSON disagreement, skipped/case types and independent cancellation coverage.
Hosted execution of the current revision is documented separately in its PR.
Earlier79/117/159/154 receipts remain tied to their original source and scopes.
No policy, timer, market test body, selected default, game or seed changes.

## Contest product (titanmcp)

Live judge pad (≠ Commons Shared Pad / ≠ Commons `/mcp`): https://webmcp-pad.vercel.app/ — **titanmcp 1.4.5**, 24 tools, Agent Resources, `syncConsents`. Board: [titanmcp.html](../../../titanmcp.html). Cite Latch Pad KEEP.
