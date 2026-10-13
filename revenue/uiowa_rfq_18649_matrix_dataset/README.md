# UIOWA-035 — Editable, exportable twelve-cell assessment dataset

**PROPOSED ASSESSMENT TOOLING / SYNTHETIC DATA / NOT A UNIVERSITY FINDING.**
Every group characterization, evidence reference, strength, gap and next step in the supplied fixture is fiction.

Original dataset, model, editor, search, generator and 54-test suite: **OP5-GRANITE / Claude Opus 5**, [donor commit 94e804c8](https://github.com/woahwhattheheck/commons/commit/94e804c80bebf07d3571b1918c5f3137695ba2c9). Lossless interchange, strict input handling, additional regressions and isolated integration: **ZZ-KESTREL-V9 / GPT-6 Astra Pro**. This is an extension of that retained product, not a competing scorer or workbench.

## Run the product

Python 3.10 or newer; standard library only, no network. Verification here used Python 3.13.5.

```bash
cd revenue/uiowa_rfq_18649_matrix_dataset
python3 matrix_dataset.py --grid --validate --round-trip
python3 matrix_dataset.py --search "privileged-access review"
python3 matrix_dataset.py --search "" --status unassessed
python3 matrix_dataset.py --dataset dataset/matrix.csv --validate --round-trip
python3 -m unittest -v test_matrix_dataset.py test_integrity.py
python3 -O -m unittest -q test_matrix_dataset.py test_integrity.py
```

The checked-in `dataset/matrix.csv` deliberately preserves GRANITE's original legacy-format fixture. New CSV exports carry the explicit lossless encoding below. Generate a pair into a chosen output directory with `python3 make_dataset.py --out /tmp/uiowa035-example`; the generator uses ordinary replacement-save semantics, so choose a fresh location when preserving earlier files matters.

## Twelve cells, not twelve forced scores

The matrix is ESS/RIS/IAM by `development`, `security`, `deployment`, and `ai_readiness`. It retains UIOWA-021's `assessment_status`, `maturity_rank`, and `maturity_label` vocabulary and five level labels. Existing `software_development` and SD/SEC/DEP/AI aliases canonicalize on input without renaming another lane.

The fixture has nine assessed cells. RIS/AI is `unassessed`; IAM/AI is `insufficient_evidence`; RIS/deployment is `not_applicable`. Each has `maturity_rank = None` and no maturity label. The fictional ESS/AI rank-1 `Absent` observation is distinguishable from all three. No unknown cell is silently assigned zero or included in `ranked_cells()`.

`Matrix.empty()` starts with all twelve unassessed cells. Missing cells remain inspectable after loading but are validation errors; neither CLI export nor save functions accept an invalid matrix. Duplicate canonical coordinates are rejected, including duplicates expressed through different aliases, rather than allowing the last row to win.

## Edit, export, reopen

Run this from the product directory. It changes only a synthetic in-memory matrix and writes to a temporary directory, not the original fixture.

```python
import os
import tempfile
import matrix_dataset as md

m = md.load_json(md.DEFAULT_DATASET)
md.edit_cell(m, "ESS", "SEC",
             evidence_refs=["https://example.invalid/evidence;revision=2"],
             gaps=["Record preserved; punctuation is part of the text"])
with tempfile.TemporaryDirectory() as out:
    csv_path = md.save_csv(m, os.path.join(out, "matrix.csv"))
    json_path = md.save_json(m, os.path.join(out, "matrix.json"))
    for reopened in (md.load_csv(csv_path), md.load_json(json_path)):
        differences = md.round_trip_report(m, reopened)
        if differences:
            raise RuntimeError(differences)
        print("12 cells retained; no round-trip differences")
```

Edits apply to a copy and store only after validation. An assessed result requires a valid integer rank, evidence and rationale. An unassessed or insufficient-evidence cell requires a resolving question. Demoting an assessed cell clears its stale rank and label. A contradictory request to demote and set a rank fails without altering the original cell. Labels are derived from rank as in the original editor.

## CSV compatibility and limits

New exports contain `CELL_FIELDS` plus `list_encoding`. Every row declares `json-array/v1`; `strengths`, `gaps`, `next_steps`, and `evidence_refs` are JSON arrays inside properly quoted CSV fields. Semicolons, commas, quotations, newlines, Unicode, empty list entries and significant whitespace survive these byte-level exports and reloads. Native JSON keeps lists as arrays.

Legacy CSV with exactly the original header and no encoding column still loads using the original semicolon grammar. The reader never guesses a grammar from a cell that merely resembles JSON. Unknown or blank encoding markers, malformed arrays, wrong row widths, duplicate headers, and unexpected columns are errors. Older exports that already lost delimiter boundaries cannot have those boundaries reconstructed by this adapter.

CSV remains **data interchange**, not a verified spreadsheet-application workflow. Import free text as text when using spreadsheet software; formula neutralization, locale-specific Excel/Sheets save behavior, and a real spreadsheet round trip were not tested. Prefer native JSON for preservation. The Python CSV reader accepts reordered headers and UTF-8 BOMs.

## Input and save behavior

Boolean and floating-point ranks are rejected rather than becoming 1 or a truncated integer. Duplicate JSON object keys, duplicate cell rows, non-finite numbers, non-string list items, and unexpected cell fields fail explicitly. Missing rows or inconsistent assessment states fail validation before an export can overwrite its destination.

Save operations validate and render first, then use a same-directory temporary file and atomic replacement. This is ordinary editor-save behavior, not concurrent-writer conflict detection or power-loss durability. The CLI refuses a destination aliasing its input or another export, including existing symbolic and hard links. Loaders allow partial matrices for inspection; callers must validate before consuming them as complete assessments.

## Proof and remaining boundaries

[VERIFICATION.md](VERIFICATION.md) records exact executed blobs, 106 normal and 106 optimized test methods, the original-fixture comparison, and the three reproduced donor failures. The same 100 seeded adversarial text cases run in both modes; they are not 200 independent cases.

This is an adapter and CLI, **not a GUI**, automatic University scoring service, or authorization to contact anyone. Browser wiring remains in the existing workbench lane. Real scope, evidence, maturity-level approval, spreadsheet-application behavior, and University findings remain unknown. No hosted-CI, deployment, or acceptance claim follows merely from the included local execution logs.
