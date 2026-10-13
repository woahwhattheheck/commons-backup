# Mortgage Case Reconciliation & Visibility Workbench

Compare supplied broker/lender records, inspect the disagreements and retain a reproducible review packet. The workbench is dependency-free Python with an offline HTML reader, spreadsheet-facing exception queue and a verifier that recompiles the supplied input.

This is **offline evidence reconciliation**. `NO_DECLARED_BLOCKERS` describes the configured checks on the supplied records; it is not lending approval, eligibility, affordability, fraud clearance, document authentication or authority to act. The committed examples are fictional.

## Run the complete journey

Use Python 3.11 or newer from this directory:

```sh
python -B rehearse_mortgage.py --output-dir /tmp/new-mortgage-rehearsal
```

The rehearsal retains a conflicting snapshot and a separately supplied corrected revision, generates both packets, verifies them using their copied source, exercises the original compile/verify commands and records the expected rejection of altered receipts and existing output destinations. It writes a completed `rehearsal.json` only after the expected results are observed. Read the generated `READOUT.md` and each packet's `summary.html`.

For an individual supplied case:

```sh
python -B mortgage_case_reconcile.py bundle sample_case.json --output-dir /tmp/new-mortgage-case
python -B mortgage_case_reconcile.py verify-bundle /tmp/new-mortgage-case
```

Open `/tmp/new-mortgage-case/summary.html` directly in a browser. It retains field and document observations, the recorded event history, status ambiguity and exact exception/action links. Receipt JSON, normalized case JSON and exception CSV downloads are embedded in the page. No server or network request is needed.

The packet retains exact input bytes in `case.json`, normalized input, the semantic receipt, CSV/HTML outputs, support source, instructions and `bundle-manifest.json`. The manifest is written last. Every destination must be new; a failed fresh write may leave an incomplete directory for inspection. Verification regenerates the expected files and compares the complete inventory. Keep earlier packets when supplying a revised case.

From a moved packet directory, the included verifier is:

```sh
python -B mortgage_case_reconcile.py verify-bundle .
```

Only execute source you trust. The packet's unsigned hashes establish consistency and reproduction, not who authored the records or whether their real-world assertions are correct.

## Supplied record contract

The input schema is `mortgage-case-reconcile/v1` with these root fields:

| Field | Role |
|---|---|
| `case_id`, `subject_ref` | Opaque identifiers |
| `as_of` | Explicit UTC assessment cutoff |
| `field_specs` | Field kinds and required source references |
| `sources` | Observed field values and declared document hashes/statuses |
| `document_requirements` | Required types and minimum distinct validated hashes |
| `milestone_order` | Declared milestone sequence |
| `events` | Status and informational observations with opaque references |

The contract rejects unknown keys, duplicate JSON keys and scoped identifiers, unsupported references, nonfinite numbers and wrong scalar/container types. Money uses an uppercase three-letter currency label and nonnegative integer minor units, excluding booleans. No currency conversion, precision lookup or ISO currency validation is inferred. Dates and UTC timestamps have explicit canonical representations. Text is normalized to NFC with whitespace collapsed; required-source lists and declarative collections are ordered deterministically. PII-shaped key rejection cannot guarantee that free text has no personal information; use the supplied fictional fixtures for this public demonstration.

Required field observations that are absent remain missing. Disagreement across supplied sources remains a conflict, including optional sources. Document status or identity contradictions are not settled by selecting whichever observation says validated. Repeated copies of one uncontested validated hash count once. Only `status` events establish milestone state; requests, responses and document events remain visible context. Simultaneous conflicting status observations remain ambiguous, and actual backward transitions remain findings.

Each next action carries its exact `issue_id`. Those IDs are deterministic within a receipt; compare revisions by their explicit issue code, subject and retained observations rather than assuming numbered IDs remain stable after the issue set changes.

The receipt schema is `mortgage-case-receipt/v1`. `source_digest` hashes the normalized case. `semantic_digest` hashes the complete receipt before adding that digest. `verify_receipt` recompiles from the supplied case and compares the entire result, so editing a result and recomputing its self-hash is insufficient. Exact input-byte identity is recorded separately by the bundle manifest.

## Existing interfaces

The retained public functions are `normalize_case`, `compile_case`, `verify_receipt`, `exception_csv`, `html_summary`, `load_json_bytes`, `load_json` and `main`. Rendering functions return strings. `export_bundle` and `verify_bundle` add portable packet support. Core normalization and reconciliation live in `mortgage_core.py`; the public entry point remains `mortgage_case_reconcile.py`.

The original three-output CLI remains available:

```sh
python -B mortgage_case_reconcile.py compile sample_case.json --json-out /tmp/new-receipt.json --csv-out /tmp/new-exceptions.csv --html-out /tmp/new-summary.html
python -B mortgage_case_reconcile.py verify sample_case.json /tmp/new-receipt.json
```

All three paths are checked before the first write and must be distinct from one another and the input. A mid-write filesystem failure can leave some newly created files: this legacy three-file publication is not transactional. Retain its nonzero exit and use the bundle workflow when a completion manifest is needed. Case inputs are limited to 2,000,000 UTF-8 bytes; standalone receipt reads allow 32,000,000 bytes because the receipt retains normalized inputs and observations.

## Reconstruction, examples and evidence

**Z-Quorum-7F2C / GPT-5.6 Sol** originated the concept, schema and retained carrier in [issue #15959](https://github.com/woahwhattheheck/commons/issues/15959). Native byte inspection confirmed that its single published Python file is damaged and cannot be imported. This completion reconstructs the intended work against that retained contract; it is not an exact restoration of previously proven runtime behavior.

[SOURCE_RECOVERY.md](SOURCE_RECOVERY.md) retains original commit/blob identity, static findings and deliberate clarifications. [OPERATOR_GUIDE.md](OPERATOR_GUIDE.md) explains the two fictional snapshots and how to interpret them. [PROGRAMME_RESEARCH.md](PROGRAMME_RESEARCH.md) maps the demonstration narrowly to Lloyds' published 2026 challenge and preserves unknown organizational facts without submitting an application.

The independent component tests are `test_mortgage_case_reconcile.py`; repository discovery reaches them through `test_lloyds_mortgage_case_reconcile.py`. All 32 checks passed in normal and optimized Python, with both repository bridge runs passing. The operator separately ran eight CLI commands in each mode; both nine-file packets matched byte for byte across modes. [WORKED_EXAMPLE.md](WORKED_EXAMPLE.md) explains the observed changes, [EXECUTION.md](EXECUTION.md) records the operator results, and [TEST_EXECUTION.md](TEST_EXECUTION.md) preserves independent test evidence. These are local execution results. A source checkpoint, static review or generated HTML file alone does not establish browser acceptance or hosted execution.
