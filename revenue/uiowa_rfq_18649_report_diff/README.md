# Inspection revision review

An offline comparison tool for two **real workshare-compiler inspection reports**.
It identifies which evidence records and assessment cells changed, keeps both
original report receipts, and produces a focused review queue. It does not replace
the compiler, assign maturity, authenticate evidence, or transfer analyst notes.

Operation: `uiowa-report-diff-zz-quartz-20260919`  
Builder: ZZ-QUARTZ / GPT-6 Astra Pro

## Run a complete fictional rehearsal

From this directory, with Python 3.10+ and the sibling
`../uiowa_rfq_18649_workshare/` directory present:

```sh
python synthetic_demo.py /tmp/uiowa-quartz-rehearsal
python review_diff.py verify \
  /tmp/uiowa-quartz-rehearsal/before.json \
  /tmp/uiowa-quartz-rehearsal/after.json \
  /tmp/uiowa-quartz-rehearsal/delta.json
python -m unittest -v test_review_diff.py
python -O -m unittest -v test_review_diff.py
```

The rehearsal directory must not exist. It contains two genuine parent-compiler
JSON reports, their canonical JSON delta, and a readable `review.md`. There are no
third-party Python packages, network calls, services, or live-system operations.
Python 3.13.5 on Linux was exercised; other versions/platforms were not executed
in the recorded validation run.

Everything in this rehearsal is **synthetic**. The University label is required
by the parent's solicitation schema, not a claim that any record describes the
University. The fictional prime, references, observations, and record content
are invented solely for repeatable tests.

### What the rehearsal demonstrates

The original report has one intentionally missing IAM AI-readiness cell. The
revision changes an ESS software source, removes ESS security evidence, relocates
one RIS deployment record to IAM, changes a RIS security reference, retains a
conflicting IAM software account, and advances the generation binding of all
remaining records. The persistent missing cell remains visible.

Expected result: **12 cells, 6 changed cells, 3 changed statuses, 5 substantive
source-record changes, 7 generation-only rebindings, and 7 review items**. Moving
one source affects two cells; therefore changed-source and changed-cell counts
are intentionally different. The expected delta receipt is
`78444ec8173a84d328f6b22cc1d81cdff9843f0387d7751def319240c6f8b726`.
The demonstration has no validated maturity improvement, approval, payment, or
University finding.

## Compare supplied reports

Create both comparison views in one invocation:

```sh
python review_diff.py bundle before.json after.json /tmp/inspection-revision-new
```

The new directory contains `delta.json`, `review.md` and a final `manifest.json`.
The bundle command performs the existing parent-semantic comparison once, then
renders both views from that same computed result. It preserves both original
report receipts and the canonical diff receipt. The manifest binds each output's
exact byte count and SHA-256; all external-authority fields remain false.

Keep both original reports alongside your working material. They are not copied
into the bundle, and the manifest does not replace them for later verification.
Validation and rendering complete before the new directory is created. If an
output write is interrupted, retained files without the final manifest are an
incomplete bundle. Existing destinations are never overwritten or deleted.
Success exits 0; invalid reports or I/O failures exit 2.

The supplied fictional before/after reports produced the same canonical delta
receipt shown above, paired with the readable review and manifest. This is
output packaging, not another assessment engine or a new review/approval stage.

Existing single-output commands remain available:

```sh
python review_diff.py compare before.json after.json delta.json
python review_diff.py compare before.json after.json review.md --format markdown
python review_diff.py verify before.json after.json delta.json
```

Every output path must be new. Existing files, including either input, are never
overwritten. A failed comparison does not create an output. A later disk/write
failure can leave a partial newly created file; publication is not a multi-file
transaction and no concurrent-filesystem custody guarantee is asserted. The
synthetic generator similarly refuses an existing directory and may leave its
new directory incomplete after an I/O failure.

Inputs are bounded at the parent's 2 MiB limit, must be regular UTF-8 JSON files,
and reject duplicate object keys and non-finite numbers. On systems with
`O_NOFOLLOW`, final-component input symlinks are rejected. Parent-directory
symlinks and concurrent filesystem mutation are outside this tool's custody
scope. POSIX outputs are created with mode 0600, subject to the process umask.
CLI exit codes are 0 for success and 2 for invalid comparison/input or I/O failure.

## Meaning of the delta

`source_changes` distinguishes added/removed IDs, content-digest revisions,
cell reassignment, changed references, assessment-record edits, evidence metadata
edits, and generation-only rebinding. A source can have multiple change kinds.
Changed field **names**, record hashes, content hashes, and cell bindings are
retained; raw claims, source references, and numeric source assessments are not
copied into the delta. IDs and hashes can still be sensitive and must not be
published from private data without appropriate permission.

`cell_deltas` always contains the exact twelve cells, including unchanged ones.
`changed_source_ids` includes substantive additions/removals/edits touching either
side of that cell. `evidence_changed` means an **evidence record changed**, not
necessarily its underlying document content; inspect the source change kinds for
that distinction. Generation-only rebinding changes record hashes and receipt
bindings but does not pretend every practice changed. The original source IDs
and hashes remain available on both sides.

A status or reason change without a substantive source-record change is labeled
`EVALUATION_WINDOW_EFFECT` when the stored evaluation time changes. Aging evidence
is not a practice regression. These are historical inspection times, not an
independent current-time check.

`review_queue` contains suggested questions for changed evidence, changed holds,
and persistent missing/conflicting/stale evidence. Persistent holds survive an
otherwise empty delta. An absent record never becomes a zero maturity score, and
removing a conflicting record never automatically becomes a verified improvement.
No additional approval workflow or permissions are created by these suggestions.

Different IDs with identical content remain added/removed records. A changed
reference is not proof of a rename. Document-level duplicate/version lineage is
outside this tool's scope; compare assessment-report changes here and use the
separate evidence-lineage work for document identity conclusions.

## Parent contract and integration

The tool imports the sibling parent's `workshare_contract` and
`workshare_verify.verify_report_integrity` and performs a **full semantic
recompile of both original reports**. It does not accept the browser's
`SYNTHETIC_UI_DEMO_NOT_COMPILER_OUTPUT` object or bypass receipt checks.
Only `UNTRUSTED_INSPECTION` mode is supported. Both reports must describe the same
engagement, and the first stored evaluation time cannot be later than the second.
The canonical parent dimension is **`software`**, not `software_development`.

```python
from pathlib import Path
from review_diff import compare_reports, verify_diff, render_markdown, write_bundle

delta = compare_reports(before_report, after_report)
verification = verify_diff(before_report, after_report, delta)
markdown = render_markdown(before_report, after_report)
manifest = write_bundle(before_report, after_report, Path("new-review-bundle"))
```

Callers must not mutate their input objects concurrently. Returned objects do not
alias either input. Rendering accepts the original reports, not an unchecked
delta. The canonical delta hash uses the parent's sorted compact UTF-8 JSON
encoding, including its final newline, excluding only `diff_receipt_sha256` from
the hashed object. **Verifying the hash alone is insufficient:** `verify_diff`
recomputes the complete delta from both verified originals, catching fabricated
rows even when their self-checksum has been recomputed.

Workbench and review-cycle adapters can use `before.report_receipt_sha256`,
`after.report_receipt_sha256`, and the affected cell/source IDs to propose review
work. This tool deliberately does not copy a disposition or note onto a different
receipt. It neither changes the workbench's existing state nor auto-resolves a
review disagreement. The integration kit can consume this library without a new
assessment engine or separate network service.

## Validation and limits

`VALIDATION.json` binds the tested source files and the eight parent-module Git
blobs. The 35-test suite executes the real compiler and verifier, including normal
and optimized subprocess CLI paths. It covers chronology, engagement mismatch,
source removal/addition/reassignment, reference/claim/metadata edits, generation
rebinding, aging, persistent gaps, conflict resolution, malformed inputs, file
non-overwrite, and rehashed report/delta tampering. Tests do not prove evidence
truth, currentness, commercial acceptance, full-repository CI, or every platform.
All external-authority fields in the derived output remain false.
