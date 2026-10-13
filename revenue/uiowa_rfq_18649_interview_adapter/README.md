# UIOWA-034 — interview capture without losing disagreement

A role-based, multi-participant capture template and executable notes-to-records adapter. Start with [the three-stage worked example](WALKTHROUGH.md), the [capture template](templates/interview_capture.md), or the [actual baseline report](examples/session_report.md).

**All supplied sessions and sources are fictional.** No interview was conducted or scheduled. This tool organizes declared accounts and source-register links; it does not authenticate artifacts, decide which account is true, establish University findings, or evaluate named individuals.

## Run the actual workflow

Python 3 standard library, exercised on Linux/Python 3.13.5. From this directory in an existing authorized cloud checkout:

```sh
python3 interview_adapter.py import --out /tmp/uiowa034-capture-NEW
python3 rehearse_capture.py --out /tmp/uiowa034-rehearsal-NEW
python3 -m unittest discover -v
python3 -O -m unittest discover -v
```

Use a new destination each time. `import` and `check` accept a new or empty directory, but never a directory with existing files; `rehearse_capture.py` requires a new directory. Nothing should run on Bryce's machine. From the repository root, `python3 -m unittest -v test_uiowa034_interview_capture` runs the component in separate normal and optimized child processes, avoiding cross-lane import collisions.

To review a copy of a captured session rather than the baseline:

```sh
python3 interview_adapter.py check --session /path/to/session.json \
  --register /path/to/source_register.json --out /tmp/uiowa034-review-NEW
```

Both commands produce the same reports. Exit **0** means no error diagnostic, **1** means review issues with reports retained, and **2** means input/output refusal. A completed capture is not a settled assessment. `--out` is now required; the original implicit overwrite of `examples/` is intentionally removed.

## Read the four outputs together

`evidence_records.json` retains records, diagnostics and coverage; `evidence_records.csv` carries the existing 16-column record contract; `session_report.md` is the readable account-by-question report. New `capture_review.json` binds the exact consumed input bytes, output hashes, total notes and imported records, all unimported note objects, and original artifact references. It keeps `source_authenticity_established` and `finding_verified` false. Do not detach it from the other three outputs.

The legacy status vocabulary is unchanged:

| Status | Meaning in this adapter |
|---|---|
| STATED | Role-attributed testimony, without a specific instance or usable artifact link. |
| ILLUSTRATED | A specific example was supplied, still the participant's account. |
| CORROBORATED | A declared document/system-export reference has a usable register entry; eligible for assessor review, not verified by this tool. |
| DISPUTED | A disagreement is declared. Both imported accounts, or the named missing counterpart, remain visible. Neither account is promoted. |

`supports_finding=true` is the original compatibility field for CORROBORATED only. It must not be interpreted as a finding verified by this adapter: no cited artifact is opened or its content compared with the statement. The report prints this limit. Source kind must explicitly be `document` or `system_export` and have a nonempty locator; interview/testimony, unknown kind or incomplete metadata cannot confer corroboration. Other source kinds require an explicit reviewed extension.

## Capture and transfer contract

Use roles, not personal-name/contact fields. `templates/session.schema.json` is a field reference, not a formal JSON Schema validator. Identity-bearing lists must contain unique nonempty IDs; duplicate or NFC-equivalent IDs, duplicate JSON members, nontext capture fields, empty statements and non-finite numbers are refused before indexing. A self-disagreement is refused as not a second account. Missing attribution/question references produce visible diagnostics and preserve the complete unimported note in the capture review.

Unanswered questions remain NOT_COVERED, not practice gaps. Only imported records contribute to coverage. A missing disagreement counterpart blocks promotion even when the note has a valid artifact reference. Arriving counterpart material clears the missing-record diagnostic, not the disagreement itself; see the worked example.

Input JSON is read once per file, bounded at 4 MiB; the same captured bytes feed parsing and the SHA-256 receipt. Text in record exports follows the original NFC normalization convention. Exact raw source hashes and unimported objects preserve the capture boundary; normalized exports are not claimed byte-identical transcriptions.

CSV keeps `\N` as the null convention, escapes literal leading backslashes, preserves empty strings separately, and prefixes spreadsheet-formula-shaped text. Consumers must use this declared grammar rather than guess that an empty field means null. Actual Excel/Sheets import behavior has not been tested. The JSON is the structured reference.

## Publication and limits

Reports render in a private temporary directory before publication. Existing files, nonempty output directories and symlinked output paths/ancestors are refused; final files are created exclusively, and the complete receipt is written last. A rendering error creates no destination. This is not an atomic directory transaction or a defense against a hostile concurrent filesystem actor. An I/O interruption can leave partial files without a complete receipt; retain them for diagnosis and choose a new private destination. No deletion/force-overwrite escape hatch exists.

The good session's JSON and CSV remain byte-identical to FLINT's original examples. The Markdown adds explicit interpretation limits; the new capture-review receipt and changed-input rehearsal are additive. See [execution and exact source identities](EXECUTION.md) for actual test scope, including baseline failures and untested boundaries. Real source-content corroboration, adjudication, full common-register integration, chronology validation, native Windows execution, hosted CI and human usability testing are not established by these tests.

Original adapter, template, fixtures and 25 tests: **OP5-FLINT**, source commit `8f063baa624e8e38116e329dc4ee994e06af5367`. Capture-integrity repair, 26 added tests, runnable rehearsal and integration: **ZZ-KESTREL-Q9F2 · GPT-6 Astra Pro**, operation `uiowa034-integration-kestrelq9f2-20260919`. Work is coordinated in the original UIOWA-034 task thread, not a later broadcast-reply timestamp.
