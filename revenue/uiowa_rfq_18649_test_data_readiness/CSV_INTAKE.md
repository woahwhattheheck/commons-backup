# Editable CSV to an evidence-preserving assessment

From this component directory, keep the starter untouched and use a new JSON path:

```sh
python3 catalog_from_csv.py catalog_template.csv --as-of 2026-09-19 --label 'Synthetic starter' --output catalog.new.json
python3 test_data_assessor.py catalog.new.json
python3 test_data_assessor.py catalog.new.json --format json
```

The first command converts; the next commands run the existing assessor and print
its Markdown or JSON report. No account, network access, dependency installation,
new evaluator, or private University records are needed. The assessment date is
explicit, never inferred from the clock. The starter's one fictional ESS row has
seven EVIDENCED checks, zero OBSERVED_GAP and zero UNKNOWN at this date.

## Conversion rules

Use the exact starter headers. `dataset_id`, `service` and `purpose` are required,
nonblank fields. Service is exactly ESS, RIS or IAM. Optional blank cells and absent
optional columns are omitted from the typed catalog, not converted to false, zero,
null or an empty inventory. Whitespace-only supplied known cells are rejected;
otherwise text is retained without stripping, case folding or Unicode normalization.
The existing assessor still applies its own documented interpretation.

Boundary cases use the starter's semicolon separator. A whole cell `[]` explicitly
records an empty list; a blank cell records unavailable evidence. Empty entries
inside a semicolon list are rejected. Identities, spaces within nonblank identities,
ordering and duplicates are retained. `[]` is reserved as the whole-cell empty
marker; a literal sole `[]` identity or an identity containing a semicolon requires
the direct JSON path. No escaping convention is guessed.

Only lowercase `true` and `false` declare cleanup applicability. Dates must be real
ASCII `YYYY-MM-DD` calendar dates; future dates are preserved so the assessor can
report them as UNKNOWN. Day counts are nonnegative ASCII integers; refresh cadence
must exceed zero. Estimated hours accept nonnegative finite decimal/exponent numbers;
values that cannot round-trip through JSON without decimal-value loss are rejected.
Original numeric spelling is retained even when `030` becomes the integer `30`.

Quoted commas, quoted embedded newlines, Unicode, LF/CRLF and an optional UTF-8 BOM
are supported. The input limit is 8 MiB; the standard CSV field-size limit also
applies. Duplicate, blank or padded headers, blank/ragged records, invalid UTF-8,
malformed CSV, invalid known cells and a header-only catalog reject the conversion.
Duplicate dataset IDs are retained as separate ordered records, not deduplicated.

## Source retention and output safety

The additional `_csv_source` block is allowed by the existing schema and ignored by
the assessor. It retains exact input bytes as base64, their SHA-256, original header
order, each logical record's original decoded cells, one-based physical line spans,
and the corresponding zero-based dataset index. Recover the exact source with
`base64.b64decode(catalog['_csv_source']['bytes_base64'])`. This includes the BOM
and original quoting/line endings, unlike reconstructed CSV.

Unknown columns appear in `unevaluated_columns` and remain in the source cells and
bytes; they are not silently treated as assessed evidence. The converted JSON
therefore contains the original evidence and is not a redacted/public-safe export.
Keep private inputs and converted catalogs out of this public repository.

The importer validates and serializes everything before opening its required
`--output` path exclusively. Existing files, directories, source aliases, hard
links and final-path symbolic links are refused. Exit 2 reports failure without a
success message. A partial newly created output is retained on a later write error;
choose a new filename after inspecting it. This is no-overwrite protection, not an
atomic durable-save or adversarial ancestor-swap guarantee. Do not use shell output
redirection for conversion: the shell can truncate a file before Python starts.

The assessor's separate `--output` path may replace a distinct regular report,
but refuses source-catalog aliases and symbolic-link outputs. It stages the report
before replacement; see [report preservation](OUTPUT_PRESERVATION.md). The commands
above print assessment results. The CSV importer itself never replaces a file.
