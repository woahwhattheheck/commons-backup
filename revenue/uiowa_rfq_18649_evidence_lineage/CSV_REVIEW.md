# Go directly from CSV exports to an evidence review

`csv_review.py` accepts two source inventories and an optional citation table, converts their explicit fields to the existing manifest contract, then calls the existing comparator and general HTML renderer. No JSON manifest needs to be hand-written. The result is the same self-contained review described in [GENERAL_REVIEW.md](GENERAL_REVIEW.md).

## Run

Python 3.10 or later, standard library only. From the repository root:

```sh
python revenue/uiowa_rfq_18649_evidence_lineage/csv_review.py \
  /path/to/before.csv /path/to/after.csv \
  --findings /path/to/citations.csv \
  --before-id collection-before --after-id collection-after \
  --output /path/to/NEW_REVIEW.html
```

The default is **private**. Use `--data-kind synthetic` only for a genuinely fictional collection. This is an operator label, not content detection or permission to publish. Omit `--findings` when no citation table is supplied; zero supplied finding rows is not proof that none exist elsewhere.

Open the new HTML in a browser. No server, account, network access or package installation is needed. The page provides searchable change/citation rows, permanent anomalies, full retained metadata, absent records, duplicate groups, successor branches, full-report printing and native comparison JSON download.

## Source inventory columns

Both inventory CSVs require these exact, case-sensitive header names:

| Column | Meaning |
| --- | --- |
| `record_id` | Explicit identity of this source record. Unique within each inventory. |
| `document_id` | Supplied logical document identity across versions; not inferred from title. |
| `version` | Opaque supplied label; never sorted to infer succession. |
| `title` | Supplied display title. |
| `location` | Supplied source location, retained as text and not opened or followed. |
| `sha256` | Supplied lowercase, 64-character content digest. |

Optional columns are `metadata_json`, containing a JSON object, and `supersedes_json`, containing a JSON list of explicit `{record_id, sha256}` predecessor references. Empty cells mean an empty object/list respectively. Use ordinary CSV quoting for JSON cells. The existing engine validates predecessor shapes, rejects cycles and preserves unresolved branches. It does not infer a predecessor from a later-looking label.

Every other column is retained under the record's `csv_columns`, including empty cells. It is not discarded or silently promoted into identity, approval or findings. CSV records remain text: `00017` stays `00017`, and date-like values, long integers and formula-like strings are not converted or executed. Structured values are parsed only inside the two explicitly named JSON columns.

Hashes in the inventory are supplied assertions. The command does not compute them from the named source locations. To bind actual source bytes, use the existing [snapshot workflow](README.md#hash-source-files-without-modifying-them) with an explicit source collection. Never fill a missing digest with an invented value just to get a report.

## Finding/citation columns

The optional citation CSV requires `finding_id`, `record_id`, `sha256` and `locator`. Each row normally supplies one citation. Repeated `finding_id` values explicitly group citations under the same finding; citation order is retained, and identical citation rows are not silently de-duplicated.

An optional `finding_metadata_json` column holds a JSON object describing the finding. Repeat the same metadata on every row belonging to that finding. Conflicting metadata is an error, including typed differences such as `true` versus `1`; a blank metadata cell is an empty object, not an implicit carry-forward of a previous cell.

Additional columns belong to that row's citation and are retained as `csv_columns`. Put finding-wide prose in `finding_metadata_json` rather than expecting the adapter to infer its scope.

To represent a finding with no supplied citations, include exactly one row with its `finding_id` and leave all three citation fields (`record_id`, `sha256`, `locator`) empty. Extra fields from that row are preserved as `uncited_csv_columns` on the finding. Partly filled citation fields, repeated uncited markers, or mixing an uncited marker with citation rows are errors rather than guessed interpretations.

## Input and output behavior

Inputs must be UTF-8 CSV, optionally with a UTF-8 byte-order mark. Commas, quotes and embedded line breaks follow the standard CSV parser. Headers are not trimmed or renamed: ambiguous duplicate/blank headers, missing required columns and rows with a different number of cells are rejected with a diagnostic. Physically blank lines are ignored; a row containing named empty cells is not silently discarded.

Input files are bounded to 16 MiB each. The parser temporarily raises its standard-library field-size limit to that bound and restores it afterward. Use a quiescent collection; this CLI is not an adversarial filesystem snapshot mechanism. As with any use of Python's process-wide CSV field-size setting, concurrent embedded callers should serialize the table-read operation.

The converted input retains the original header sequence and the SHA-256 of each exact CSV file under `csv_source`. The HTML's comparison bindings refer to the resulting canonical JSON manifests/findings, not to CSV formatting. The downloadable JSON preserves the converted inputs and comparison, but is not a raw CSV archive; retain the original exports separately when their exact bytes are needed.

Output creation is exclusive. Existing output paths, including inputs and occupied/dangling final symlinks, are not replaced. The parent directory must exist. An interrupted or failed output write can leave a partial newly created file; choose another destination after addressing the cause. Nothing automatically deletes files.

Exit `0` means the report was written, even when follow-up rows remain. Exit `2` means invalid or unreadable input, or an output failure. An HTML review does not authenticate source hashes, validate passages against locators, resolve findings, approve a version or certify an assessment.

## Scope

Only this CSV adapter and its guide are added. The comparator, general renderer, fixed seven-case demonstration, assessment workbench and repository workflows are unchanged. No live institutional data, external provider, account, payment or customer action is performed. Generated reviews contain full supplied metadata and must remain on an appropriate private surface.

No tests, fixtures or workflows were added or run for this publication. Operation: `yz-kestrel-ap47-lineage-csv-review-20260923`.
