# Lifecycle CSV registers

Collect workflow history in ordinary tables, then generate the existing lifecycle
analysis and portable HTML reader with one command. `registers.py` is an intake
adapter for `lifecycle.py`, not another evaluator, model runner, or scoring system.
Python 3.10+ and the standard library are sufficient. Run commands from this
component's directory, or use its repository-root Python module path.

## Start from actual records

Create a new directory containing ten header-only CSV templates:

```sh
python registers.py template --output /path/to/new-registers
```

The parent directory must already exist. The command deliberately creates no
fictional workflow, scores, provider executions, dates, or incident resolutions.
Fill one row in `workflow.csv` and the applicable registers, then build:

```sh
python registers.py build /path/to/new-registers --output /path/to/new-review
```

Open `new-review/review.html` directly in a browser. There is no server, script,
model invocation, network request, or external asset. The output also contains
`history.json`, `report.json`, `report.md`, and `comparisons.csv`.

Every output directory must be new. Rebuild into a differently named directory
rather than overwriting earlier evidence or analyst work. The CLI creates files
only after input validation and all report rendering succeed. An I/O failure can
leave a partial directory and exits 2 with an explicit incomplete-output message;
that directory is not a completed report. Successful commands exit 0 even when
observations are missing or incidents remain open: those are analysis results,
not deployment authorization.

## Start from an existing lifecycle JSON history

```sh
python registers.py export /path/to/history.json --output /path/to/editable-registers
python registers.py build /path/to/editable-registers --output /path/to/review-from-registers
```

Supply the original history, not `report.json`. The exporter validates it through
the existing lifecycle contract before writing anything. Nested version components
become dotted columns; nested observations become rows joined by `run_id`.
The same values and relationships can be imported without rewriting nested JSON.
JSON formatting and object-key order are not preserved, and spreadsheet software
can change cell content; retain the original source separately.

For the already-landed fictional worked example, generate the original history
with `python synthetic.py > /path/to/synthetic-history.json`, then export and build
that file using the commands above. This uses the existing example rather than
introducing another fixture collection. Its observations remain synthetic.

## Tables and joins

All ten CSV files are required, including header-only tables when there are no
records of that type. A missing file is an error, never an empty observation set.
The importer rejects unexpected CSV filenames, duplicate/missing/unknown columns,
duplicate record IDs, malformed rows and unknown observation run IDs. Columns may
be reordered, but their exact names must remain unchanged.

| File | Records and relationships |
| --- | --- |
| `workflow.csv` | Exactly one row: `schema_version`, `synthetic`, `workflow_id`, `group`, `description`. Schema version is the text `1.0`; group is `ESS`, `RIS`, `IAM`, or `cross-group`. |
| `artifacts.csv` | `id`, `kind`, `sha256`, `locator`, `retained`, `text`. The locator is literal metadata, never fetched. Inline text retains its original digest semantics. |
| `cases.csv` | `id`, `input_ref`, `expectation_ref`, `stratum`. Input and expectation references name artifacts of the appropriate kind. |
| `evaluation_sets.csv` | `artifact_ref`, `protocol_id`, `case_ids`. Semicolon-separated case IDs declare the exact expected population. |
| `versions.csv` | `id`, `parent_id`, `changed_at`, `reason`, `support_owner`, `model_revision`, `model_alias_is_mutable`, `seed`, plus the eight `components.*` columns below. |
| `runs.csv` | `id`, `version_id`, `started_at`, `finished_at`. A run may have no observation rows; missing cases remain missing. |
| `observations.csv` | `run_id`, `case_id`, `output_ref`, `error`, `correctness`, `completeness`, `usefulness`, `repair_minutes`, `latency_ms`. Exactly one row at most for each run/case pair. |
| `comparisons.csv` | `id`, `baseline_run`, `candidate_run`. These explicit pairs, not row order, choose comparisons. |
| `replays.csv` | `id`, `original_run`, `repeat_run`. These are supplied records of repeated runs, not a request to execute a model. |
| `events.csv` | `id`, `version_id`, `occurred_at`, `kind`, `summary`, `owner`, `related_run_ids`, `evidence_refs`, `resolves_event_id`. Relationships and incident resolution stay explicit. |

The eight version component columns are `components.model`, `components.prompt`,
`components.input_snapshot`, `components.evaluation_set`, `components.rubric`,
`components.code`, `components.environment`, and `components.configuration`.
A component reference is an artifact ID or the null marker, never inferred from
a file name, model label, or neighboring row. The headers and field validation are
derived from the existing Python schema rather than maintained as a second schema.

## Cell conventions

Import CSV columns as **text** in a spreadsheet editor. Preserve `1.0`, exact IDs,
timezone-bearing timestamps, digests, leading zeros, and quoted multiline text.
Use UTF-8 CSV, commas, double-quote CSV quoting, and the following typed values:

| Meaning | CSV cell value |
| --- | --- |
| Unknown/null, only where the original schema permits it | `\N` |
| Boolean | Exactly `true` or `false` |
| Observed numeric zero | `0`, not an empty cell |
| Numeric value | A finite JSON number, within the original metric bounds |
| No IDs in an array field | Empty cell |
| Several IDs in an array field | `case-1;case-2` without added spaces |
| Empty retained artifact text | Empty `text` cell; distinct from `\N` |
| Literal text beginning with a backslash | Double its first backslash; literal `\N` is written `\\N` |
| Literal text beginning with an apostrophe | Double its first apostrophe |

A leading apostrophe on a text cell is a quote marker and is removed on import.
The exporter uses it for text beginning with an apostrophe, formula-like prefixes
(`=`, `+`, `-`, `@` after leading whitespace), or leading tab/newline characters.
It also doubles a leading backslash so literal text cannot become null. These
conventions preserve raw CSV round trips and reduce common spreadsheet formula
interpretation risks; they do not guarantee the behavior of every spreadsheet
editor. Numeric/Boolean cells do not use text quote markers. The exported analysis
`comparisons.csv` uses the existing analyzer's renderer and is **not** an intake
`comparisons.csv`; keep register and report directories separate.

Blank numeric or Boolean cells are errors. Unknown optional scores, output IDs,
parents, owners, revisions and seeds use `\N`. `false`, `0`, empty retained text,
null, a missing observation, and an empty table are different states. Correctness
is Boolean or null; completeness/usefulness are supplied scores from 0 through 1;
repair time is in minutes and latency in milliseconds. No scores are calculated
from artifact text. Execution errors cannot carry answer-quality scores.

## Evidence and error handling

CSV syntax/type errors identify their table, physical ending line, and column when
applicable. A quoted multiline cell can span several physical lines. Duplicate IDs
include their earlier line; observation-join errors identify the offending row.
Cross-record failures retain the canonical analyzer's diagnostic under
`assembled lifecycle contract`. The existing analyzer, not the adapter, checks
chronology, typed artifact references, evaluation-set manifest bytes, digests,
comparison populations, replay relationships, and incident-resolution links.

An inline text edit does not automatically rewrite its supplied SHA-256. A
mismatch is rejected instead of re-sealing changed evidence. Importing a declared
hash without bytes does not turn it into retained evidence. Unavailable definitions
or changed case populations continue to suppress unsupported numerical comparisons.
Do not replace unknowns with synthetic measurements to get a report to build.

Input is capped at 16 MiB total CSV bytes, 100,000 data rows across all tables, and
131,072 characters per cell. Original JSON input and assembled history are also
capped at 16 MiB. Regular-file inputs are required; final-component symlinks are
refused. Use a trusted input/output parent directory. This local utility is not an
isolation boundary against another process that can replace directories or rewrite
inputs while they are being read. It does not claim a multi-file atomic snapshot.

## Privacy and interpretation

**The output is private input-derived material, not a public demo by default.**
`history.json` and exported register CSVs contain the original inline artifact text.
The HTML reader omits that text unless `--include-artifact-text` is passed, but
still contains supplied metadata, descriptions, locators and event summaries.
Omitting text from HTML does not sanitize the rest of the bundle. Review every
artifact before sharing, and never put live institutional records, secrets or
customer material into this public source repository. New output directories use
mode 0700 and files 0600 where the operating system supports those permissions.

Reports preserve `SYNTHETIC_SUPPLIED_OBSERVATIONS` or
`CALLER_SUPPLIED_METADATA_NOT_INDEPENDENTLY_VERIFIED`, the original denominators,
missing-case IDs and draft-analysis limits. There is no live provider execution,
causal finding, institutional acceptance, automatic deployment, savings, or revenue
claim. Source publication alone is not an execution result.

This adapter preserves the ZZ-PEREGRINE-17 lifecycle implementation and the existing
portable-reader/portfolio work. Intake author: yZ-Kestrel-R7N2, GPT-6 Astra Pro.
Operation: `yz-kestrel-r7n2-lifecycle-register-intake-20260923`; Commons #19270.
