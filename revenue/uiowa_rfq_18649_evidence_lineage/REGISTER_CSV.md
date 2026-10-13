# Import evidence registers from CSV

`register_csv.py` connects an existing spreadsheet or register export to the
lineage comparator. It does not replace the comparator, infer document identity,
infer succession from a filename, or alter an evidence file. Python 3.10 or
newer and the standard library are sufficient.

From this directory, compare two explicit register exports in one command:

```sh
python register_csv.py compare before.csv after.csv \
  --before-id intake-before --after-id intake-after --data-kind private \
  --before-root /approved/evidence/before \
  --after-root /approved/evidence/after \
  --findings /approved/evidence/findings.json \
  --output-dir /approved/reports/lineage-review-01
```

The output directory must not exist, and its parent must already exist.
`--findings` is optional. The command creates four files after both registers,
optional source snapshots, findings and comparison have been processed:

- `before.json` and `after.json`: complete manifests compatible with `lineage.py`.
- `review.json`: the existing comparator's full report, including retained
  manifests, citation impacts and known lineage.
- `review.md`: the existing readable comparison report.

No separate receipt, test harness, workflow or scheduled process is created.
The current engine's report format is unchanged; existing JSON consumers can
use `review.json`. Consult `RUN_READER.md` for the existing offline reader.

## Register columns

The first CSV row must contain these exact column names, in any order:

| Column | Required meaning |
| --- | --- |
| `record_id` | Explicit record identity, unique within this register. |
| `document_id` | Explicit logical document identity across revisions. |
| `version` | Opaque version label; it is never numerically sorted or inferred. |
| `title` | Human-readable source title. |
| `location` | Explicit source location. With a source root, this must be a regular, root-relative file. |

Optional columns:

| Column | Meaning |
| --- | --- |
| `sha256` | Lowercase SHA-256. Required per row when no source root is supplied. With a root, a nonempty supplied digest must match the actual bytes. |
| `metadata_json` | A JSON object. Blank means no supplied metadata. |
| `supersedes_json` | A JSON array of explicit predecessor objects containing `record_id` and the exact predecessor `sha256`. Blank means no supplied declaration. |

Every other export column is retained as a string under each record's
`register_columns`, including empty strings. This preserves owner, department,
period and other export columns without guessing their meaning or treating them
as additional evidence. Existing nested metadata remains separate.

The tool preserves string content, including leading zeroes, Unicode and quoted
multiline cells. It does not trim identifiers, convert spreadsheet dates, cast
numeric-looking IDs, repair malformed UTF-8 or evaluate formulas. Ensure the
spreadsheet export itself has not already changed an identifier or digest.

CSV is comma-delimited with standard double-quote escaping. UTF-8 with or
without a leading BOM is accepted. Header duplicates, missing required columns,
unequal row widths, empty required cells, duplicate record IDs, malformed JSON,
duplicate JSON keys and non-finite JSON numbers are errors. A genuinely empty
line is ignored; a row of empty cells is not.

For example, an operator-authored before register might be:

```csv
record_id,document_id,version,title,location,owner
OPS-001-v1,OPS-001,v1,"Operations handoff, first export",manual-v1.txt,Operations
```

An after register might contain:

```csv
record_id,document_id,version,title,location,owner
OPS-001-v2,OPS-001,v2,"Operations handoff, revised export",manual-v2.txt,Operations
```

Those examples require the two named files under the supplied roots. They do
not assert their contents or digests. The common `document_id` supplies logical
identity; the `v2` label alone does **not** declare succession. The engine reports
changed content without an explicit predecessor declaration as such. To declare
succession, supply the original record ID and actual digest in
`supersedes_json`, using normal CSV quoting for its JSON text. Do not substitute
an invented digest or infer a predecessor from row order.

## Convert one register first

Create a manifest without comparing it:

```sh
python register_csv.py manifest before.csv \
  --collection-id intake-before --data-kind private \
  --source-root /approved/evidence/before \
  --output /approved/reports/intake-before.json
```

The output file must not exist. This lets the custodian inspect the actual
source digests before supplying predecessor declarations or finding citations.
The manifest can be passed directly to the already-existing `lineage.py
compare` command. Collection IDs and data kind are explicit operator inputs,
not guessed from a filename or verified as institutional facts.

A register whose every row already contains a digest can omit its source root:

```sh
python register_csv.py manifest retained-export.csv \
  --collection-id retained-export --data-kind private \
  --output /approved/reports/retained-export.json
```

Without a root, digests are retained assertions, not byte verification. Before
and after can independently use supplied digests or source snapshots. Their
manifest `hash_basis` values retain this distinction. A blank digest without a
root is an error, never an automatically generated digest of the filename.

## Output, privacy and failure behavior

Each input CSV and each snapshotted source file uses the engine's 16 MiB bound.
JSON findings use the engine's existing strict loader. The manifest includes
the CSV's basename, exact input-byte SHA-256 and header names for reproducibility;
that digest is not a signature or source-authentication claim.

All outputs can contain private identifiers, titles, paths, custodian metadata
and citation text. Keep private registers and reports on the approved evidence
surface; do not commit them to the public repository. `--data-kind synthetic`
is only for genuinely fictional data. The flag records an operator statement,
not an automatic privacy classifier or verified provenance.

Source-root processing delegates to the existing snapshot implementation. It
hashes only explicitly named files, checks its supported path and incidental
change conditions, and never discovers, downloads, renames or rewrites sources.
Use a quiescent collection; this is not an adversarial filesystem-custody or
source-authentication protocol.

Exit `0` means import/comparison processing finished, including when conflicts,
missing evidence or unresolved branches were found. It does not mean an
assessment, citation, document version or deliverable was approved. Exit `2`
means invalid/unreadable input, an existing output, or a write failure.

All comparison payloads are rendered before the new output directory is
created. Individual files use exclusive creation; prior files are never
replaced. A disk or filesystem error during writing can leave a partial new
file or directory. The command reports failure rather than success, does not
remove that material automatically, and never overwrites it on a retry. Use a
new output name after resolving the error. Whole-directory atomic publication
is not claimed.

The original evaluator, data contract, reader, source examples and workflows
are unchanged. This adapter adds no approval, submission, payment, commercial
or assessment authority.
