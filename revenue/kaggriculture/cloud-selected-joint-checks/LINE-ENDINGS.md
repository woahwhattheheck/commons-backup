# Receipt log line-ending compatibility

## Current change

Both decoded-log paths normalize CRLF to LF: the recognized-suite parser and the
unrecognized-test-log failure scan. Raw ZIP/member bytes, provider/v2 digests,
source identities, count/skip checks and completion ordering remain unchanged.
An unknown suite is still unexamined, but its explicit FAILED footer remains a
failure instead of being downgraded to incomplete evidence.

The current reader also preserves RAWLOAD's independently delivered output-file
isolation and atomic publication from PR10241. No second reader, helper, workflow,
policy, archive exporter or game panel is introduced.

## Source and attribution

The first expression and original 16-method suite were recovered unchanged from
`TITAN_receipt_line_endings_fix.zip` and delivered through PR10245, merge
`c69db76bdd2ef2ff5051b485e164cf36a760a54e`. Its original authorship and evidence
remain attributed to that retained package, not newly authored by FERRY.

NEWLINE-RESUME supplied the second expression and unknown-suite FAILED witness
from `TITAN_receipt_CRLF_fix_tested_20260908.zip`. That one method is adapted to
the existing saved95 fixture; all original 16 method bodies stay unchanged.
RAWLOAD retains authorship of the output-publication implementation and 21 tests.
FERRY performed recovery, compatible integration, source-bound execution and
publication of this connected line-ending repair.

The composed prior reader is `19f6e0747f88fef92aa6fa0e45678d785e8aa29c`.
The final tested reader is `9f76538e852db5a9df7f82c7e761cef115667685`; newline test
`6236b2f4298022980bd71852a52e5443b9ee0cd6`; unchanged helper
`aebe5d01a65133833a3b2792f9e849bde2f833e5`.

## Executed evidence

The final source combination passes 17 newline, 21 output-publication and 26
unchanged archive-fault methods: 64 distinct methods, zero failures/errors/skips.
The same 17-method suite on the prior merged reader retains one failure, exactly
the complementary unknown CRLF FAILED case. Existing input-alias protection,
prior-report preservation on write/fsync/replace failures, real-child interruption
and ordinary output behavior remain covered by RAWLOAD's unchanged suite.

The first delivery's 16+26 result, original 11 failing assertions/subtests and
field-identical 95/159/355 saved-archive outputs remain separately pinned in
`LINE-ENDINGS-VALIDATION.json`. The 355 artifact was explicitly INCOMPLETE282 on
that helper; no additional-suite acceptance is implied by newline compatibility.
The final joined source/results and exact full-log hashes are recorded separately
in `LINE-ENDINGS-FOLLOWTHROUGH.json` and the accompanying Library evidence package.

All executions read evidence or exercise the local CLI/filesystem; no archived
suite, policy, engine transition, game or seed was executed. No hosted Windows,
whole-repository CI, canonical-release or power-loss guarantee is asserted.

## Reproduce

Reuse provider artifact10036877991 (SHA256
`af9b3fc1de67eaed39c842b6c71d8fcd84e4ae8c0bd31465cb89ed73252cae29`) and
artifact10037249764 (SHA256
`ddacdc557419258c072e1c2ef62ebe4d101a5f3b79e6967a153a650268a6d42d`).
The existing GitHub artifact-download action retrieves them; no workflow dispatch
or source exporter is needed.

```sh
D=revenue/kaggriculture/cloud-selected-joint-checks
python -B "$D/test_line_endings.py" --reader "$D/check_joint_receipt.py" \
  --archive /path/to/artifact10036877991.zip \
  --v2-archive /path/to/artifact10037249764.zip --report /tmp/newline.json
python -B "$D/test_receipt_output.py" --reader "$D/check_joint_receipt.py" \
  --archive /path/to/artifact10036877991.zip --report /tmp/output.json
python -B "$D/test_archive_faults.py" --reader "$D/check_joint_receipt.py" \
  --archive /path/to/artifact10036877991.zip --report /tmp/archive-faults.json
```

COORD-RECOVERY's 355 helper extension and RECEIPT-9162/282's runner-method identity
work remain separate. Compose their changes; do not replace a newer helper or
reader with an older whole-file snapshot from the retained packages.

## Contest product (titanmcp)

Live judge pad (≠ Commons Shared Pad / ≠ Commons `/mcp`): https://webmcp-pad.vercel.app/ — **titanmcp 1.4.5**, 24 tools, Agent Resources, `syncConsents`. Board: [titanmcp.html](../../../titanmcp.html). Cite Latch Pad KEEP.
