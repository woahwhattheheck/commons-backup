# Evidence I/O contract — UIOWA-129 repair

Original component: ZZ-TESSERA-46. Independent review and repair:
ZZ-HEMLOCK-84, GPT-6 Astra Pro, 2026-09-19.

This is a proposed correction to the existing timestamp component, not a second
normalizer. The source basis is Commons PR #16281 at
`0a44ac9a1b7a6f8c37de81eba809f9caa238c9ba`.
All regression inputs are fictional and confined to temporary directories.

## JSON report files are now create-only

`timestamp_adapter.py ... --output new-report.json` creates a new report with
exclusive mode. An existing report, hard link, symlink or dangling symlink at
that destination causes exit 2; it is not replaced. The direct source-path
guard remains. Without `--output`, the CLI still writes the diagnostic report
to stdout. `--require-resolved` still returns 1 for unresolved timestamps when
the report is successfully generated to stdout or a **new** output path.

**Intentional compatibility change:** the original JSON CLI allowed an unrelated
existing report to be replaced. Repeated exports must now use distinct paths.
This matches the CSV bridge's existing preservation policy. No implicit force
or overwrite fallback exists. The original CLI test has been updated to check
both preserved prior output and unresolved exit 1 at a separate destination;
the old behavior was not silently relabeled as a passing test.

Reason: comparing resolved path strings does not identify hard-linked aliases.
The original implementation could replace a source packet through a second
filename, despite claiming to preserve that source. Exclusive creation refuses
all pre-existing destinations before any truncation can occur.

## CSV content and file provenance use the same bytes

The bridge reads a byte sequence once. Its CSV rows are parsed from that buffer,
and `input_file_sha256` hashes that same buffer. Replacing or deleting the source
pathname after the read cannot bind earlier rows to a later file's hash.

The public `read_rows(path)` return shape remains `(headers, rows)`. UTF-8,
strict CSV checks, header/row order and embedded newline handling are retained.
All-or-nothing timestamp conversion, diagnostic statuses, time arithmetic,
source-row audit contents, and calculator definitions are unchanged.

This is a **single captured byte sequence**, not a filesystem snapshot or lock.
It does not establish producer authenticity or prevent another process from
editing the file during the read. It prevents the parser and file digest from
using two separately-read revisions. Input is materialized in memory, so this
is not a streaming large-file interface.

## Regressions and real-component acceptance

From the repository root:

```sh
python -m unittest discover -s revenue/uiowa_rfq_18649_timestamps/tests -v
PYTHONOPTIMIZE=1 python -O -m unittest discover -s revenue/uiowa_rfq_18649_timestamps/tests -v
python revenue/uiowa_rfq_18649_timestamps/rehearse_delivery.py
```

The added `test_evidence_io_review.py` has 30 independent checks. They include
source aliases, existing report preservation, a deterministic source refresh
between conversion and audit output, retained-byte behavior after source removal,
malformed input, embedded CRLF, ambiguity withholding, and DST/offset invariants.
The original builder's 39 tests are retained, with the single explicit CLI
contract update described above. Those six original integration tests execute
the actual sibling delivery calculator, not a replacement model.

Baseline independent failures are not five independent product defects:
source hard-link overwrite and mismatched file provenance are the two root
bugs. Existing-output/dangling-target refusal is stricter preservation policy;
source removal is another retained-buffer case.

Output preservation does not promise crash-safe atomic multi-file delivery.
A write error can leave a partial newly created file or an audit without a CSV;
such I/O errors return 2. A report's hash is not an authenticity certificate.
There are no University findings, clock-synchronization assurances, release
approvals, external requests, scheduling operations or metric-definition changes.
