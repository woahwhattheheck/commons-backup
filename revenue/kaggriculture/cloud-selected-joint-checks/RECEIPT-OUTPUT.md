# Preserve evidence while writing receipt output

The existing `check_joint_receipt.py` CLI now rejects an output referring to its
input evidence ZIP, including normalized, symlink and hardlink aliases. Valid
receipts are fully staged and file-fsynced in the destination directory before
atomic replacement. Ordinary errors use the existing `ERROR` / exit 3 path;
cancellation propagates. A previous report is retained on failed publication.

The output helper follows an existing report symlink as the former direct writer
did. Atomic replacement changes the destination entry rather than writing through
an unrelated hardlink. New staged report files use temporary-file permissions.
This is not a hostile-filesystem race defense or a directory-fsync/power-loss
transaction. Uncatchable termination can leave an unreferenced stage file.

## Executed result

Exact baseline `0cc4b4ab6b3db350b06ec24bd63068b13ae17946`, from main pin
`da06913ba9ba79f26b61b66498b4523d2a162278`, has **14 failures, zero errors**
in the same 21-method suite. Candidate
`51d647c3dba941c3389e1e85b3884a3553ab6cff` passes **21/21**, zero skips.
The unchanged helper is `aebe5d01a65133833a3b2792f9e849bde2f833e5`.

The concrete original witness runs the real reader on a detached copy of artifact
10036877991 with its ZIP also named as `--json-output`: it exits 0 and reports
`COMPLETE_PASS95`, but replaces the ZIP with JSON. The source artifact remains
untouched. The new reader rejects that operation with exit 3 and preserves bytes.

The suite covers six alias forms, separate and nested reports, ordinary report
symlinks, all four original exit classes, partial writes, stage creation, fsync,
replacement, cancellation and cleanup failure. A real child exits 97 immediately
before replacement: the existing report and input stay exact, and the complete
unpublished stage remains separately visible. Mocked filesystem failures are not
presented as crashes or power-loss experiments.

`unique_object`, `read_members`, `integer` and the complete `inspect_archive` ASTs
are unchanged. Only CLI output publication changes. The supplemental helper and
its owners' method-identity / 355-suite work are not edited or credited here.
No archived test, official transition, actor, game or workflow was executed.

## Reproduce

Use the already-saved CYPRESS ZIP, artifact `10036877991` from run `34174806533`.
Its exact size is 120855 bytes and SHA256 is
`af9b3fc1de67eaed39c842b6c71d8fcd84e4ae8c0bd31465cb89ed73252cae29`.
The acceptance suite reads this existing 95-method evidence but never executes it.

```sh
python3 -B revenue/kaggriculture/cloud-selected-joint-checks/test_receipt_output.py \
  --archive /path/to/titan-existing-validation-10036877991.zip \
  --report /tmp/receipt-output-tests.json
```

For the direct consumer, use the same CLI with a distinct output:

```sh
python3 -B revenue/kaggriculture/cloud-selected-joint-checks/check_joint_receipt.py \
  /path/to/titan-existing-validation-10036877991.zip \
  --expected-sha256 af9b3fc1de67eaed39c842b6c71d8fcd84e4ae8c0bd31465cb89ed73252cae29 \
  --json-output /tmp/receipt.json
```

`RECEIPT-OUTPUT-VALIDATION.json` records the precise source, fixture, execution and
raw-log hashes. The complete baseline/candidate outputs and reproduction sources
are retained together in Bryce's Library evidence bundle. Existing archive verdicts
and source-specific method counts remain unchanged; this result is output-file
correctness, not a new CI or game-strength result.

## Contest product (titanmcp)

Live judge pad (≠ Commons Shared Pad / ≠ Commons `/mcp`): https://webmcp-pad.vercel.app/ — **titanmcp 1.4.5**, 24 tools, Agent Resources, `syncConsents`. Board: [titanmcp.html](../../../titanmcp.html). Cite Latch Pad KEEP.
