# Peer-evidence comparability compiler

An offline, standard-library analyst aid for source-linked peer research. It turns
research metadata into a reproducible source register, practice cards, metric
context table and pairwise comparison screen. It does not calculate institutional
maturity, rank universities, authenticate publications or infer Iowa practices.

Operation: `UIOWA-PEER-COMPARABILITY-COPPERFINCH-20260919`.
Builder: ZZ-COPPERFINCH / GPT-6 Astra Pro. Work record: Commons issue #16091.

## Run the complete rehearsal

Requires Python 3.10 or newer; no package installation or network connection.
From this directory, with a new output directory name:

```sh
python peer_evidence.py example.json --out rehearsal
python -m unittest -v test_peer_evidence
python -O -m unittest -v test_peer_evidence
```

Without `--out`, the compiler prints report JSON to standard output. An output
bundle contains `report.json`, `peer-evidence.md`, `sources.csv`, `records.csv`,
`metrics.csv`, `comparisons.csv` and `metric-context.csv`. The CSV files are export
views, not a second input format. The JSON retains exact nullable values and
nested source references. Existing output directories are never overwritten.
Malformed input or an I/O error returns exit status 2 and a diagnostic on stderr;
success returns 0. Validation precedes directory creation. A later filesystem
failure can leave an incomplete new directory: output writing is not a transaction.

The included four institutions, publications, practices and measurements are
**entirely fictional**. `example.org` links are placeholders, not retrieved sources.
The observed rehearsal results and facilitator exercise are in [REHEARSAL.md](REHEARSAL.md).
Do not commit private University, prime, customer, account or credential material
into this public repository. This program neither collects nor publishes input.

## Input contract, version 1.0

The accepted root keys are `schema_version`, `mode`, `as_of`, `sources`, `records`,
`metrics`, and optionally `comparisons`. All other keys are rejected. Schema
version is the string `1.0`; mode is `SYNTHETIC_REHEARSAL` or
`PUBLIC_SOURCE_RESEARCH`. The latter is a researcher label, not source validation.
`as_of` is an explicit `YYYY-MM-DD` date, not an implicit machine-clock sample.

Identifiers are unique within each entity collection and use 1–80 ASCII letters,
digits, periods, underscores or hyphens, beginning with a letter or digit. Every
key shown below is required even when its value is explicitly `null`.

| Entity | Required fields | Interpretation |
|---|---|---|
| Source | `id`, `title`, `publisher`, `url`, `version`, `published_on`, `accessed_on` | Record the actual issuer and public URL; nullable version/publication date stays unknown. Access date cannot follow `as_of`. A publication date after access produces a reconciliation note. |
| Record | `id`, `institution`, `service_context`, `assessment_areas`, `evidence_kind`, `statement`, `source_refs`, `transfer_notes`, `local_unknowns` | One bounded statement with source support, actual service boundary, proposed transfer and remaining local questions. |
| Metric | `id`, `record_id`, `metric_key`, `kind`, `value`, `definition`, `unit`, `statistic`, `population`, `collection_method`, `exclusions`, `period_start`, `period_end`, `sample_size`, `numerator_definition`, `denominator_definition`, `denominator_count`, `source_refs` | An as-reported measure, not a newly computed result. Each metric cites its own exact table/row/section rather than inheriting a whole-document citation. |

`source_refs` is a nonempty array of objects with exactly `source_id` and `locator`.
Use a section, page plus table/row, or other retrievable precise locator. The source
must exist in `sources`; duplicate source/locator pairs are rejected. A metric must
also point to an existing record. References are syntactically checked, not fetched.
No document hash, signature, identity or claim of authenticity is derived from a URL.

`assessment_areas` contains one or more distinct values from
`software_development`, `security`, `deployment_operations`, `ai_readiness`.
`evidence_kind` is one of `policy`, `reported_practice`, `measured_outcome`,
`framework`, `proposal`. Split a source into separate records when it supports
both an intended practice and an observed result; do not upgrade policy intent
merely because the same page also mentions a number. `transfer_notes` is proposed
analyst interpretation, not a finding. `local_unknowns` is a text array; an empty
array means no questions were recorded, not that local applicability is proven.

Metric `kind` is `count`, `gauge`, `duration`, `ratio` or `rate`. `value` is a decimal
string or `null`; no float conversion, unit conversion, rounding, aggregation,
annualization, plausibility validation or statistical inference is performed.
Preserve the published unit separately. Unsupported exponent/percentage-formatted
strings are rejected rather than silently normalized. Negative as-reported values
are retained, not judged appropriate for a particular metric.

All contextual metric text may be `null`. Observation dates can be independently
unknown; known dates must be valid, ordered and no later than `as_of`. Sample size
and denominator count are nullable integers from 0 through 10^12, never booleans.
Use `exclusions: null` for unknown exclusions and `exclusions: []` only when no
exclusions were declared. An array records explicit exclusions. A missing field
is a schema error; explicit `null` is retained uncertainty.

## What the comparison screen means

Every metric receives `CONTEXT_RECORDED` or `NEEDS_CONTEXT`, even with no selected
pairs. The screen requires a value, definition, unit, aggregation statistic,
population, collection method, exclusions, observation period and sample size.
Ratios/rates additionally need numerator and denominator definitions and a known
nonzero denominator count. Zero sample size is visible separately from unknown.
A supporting record not classified as a measured outcome always needs context.
These are this tool's **proposed review prompts**, not a validated scientific
completeness standard or a source's own definitions.

Pairwise comparison uses exact supplied metadata after order normalization:
metric key, kind, definition, unit, statistic, population, collection method,
exclusions and both period endpoints; ratio/rate pairs also compare numerator and
denominator definitions. A known mismatch yields `CONTEXT_DIFFERS`. With no
known mismatch but missing context, the result is `NEEDS_CONTEXT`. Otherwise it is
`ALIGNED_METADATA_REVIEW_REQUIRED`—never "comparable", "best", "pass" or "ready".
Both missing fields and mismatches are retained when they coexist. Different
sample sizes add a precision/representativeness note, not an automatic rejection.
Denominator counts need not be equal; their meanings must be recorded.

Equal wording can hide different sampling frames, instrumentation or collection
bias; different wording can describe compatible measurements. The tool does not
resolve either problem. It calculates no confidence intervals, significance,
causal effects, rankings or peer percentiles. Different periods may legitimately
support a longitudinal study, but that requires an explicit analyst method; this
screen does not silently turn them into a cross-sectional benchmark. Review the
service context and transfer limits even when metadata aligns.

When `comparisons` is absent, only metrics sharing the same researcher-assigned
`metric_key` become candidate pairs. Supply explicit pairs such as
`[["M1", "M2"], ["M1", "M3"]]` to choose the review set. An explicit empty list
means no pairs selected; it is not evidence of comparability. Self-pairs, unknown
metric IDs and duplicate unordered pairs are rejected. No transitive grouping or
clustering is inferred from pair results.

## Evidence-preserving outputs

The normalized input sorts entity collections by ID, unordered evidence areas,
local-question lists, source references, exclusions and explicit pair order. It
preserves actual text and values. Canonical UTF-8 JSON defines `input_sha256`.
Reordering these unordered collections leaves the digest and bundle unchanged;
changing a locator or another semantic value changes the digest. The digest is
**content identity, not source authentication, review approval or a signature**.
`compile_packet` does not mutate or retain aliases to the caller's input.

`report.json` is the canonical machine-readable export. Coverage contains only
counts of recorded evidence kinds by assessment area; it is not a completeness
percentage or maturity score. Source verification is always `NOT_PERFORMED`.
The result is always `PEER_CONTEXT_NOT_LOCAL_ASSESSMENT`.

CSV nulls are empty cells; nested arrays/objects are JSON text. To preserve text
interpretation in spreadsheet applications, cells whose first non-whitespace
character is `=`, `+`, `-` or `@` receive a leading apostrophe. Thus negative numeric
strings are intentionally text in CSV. JSON values remain unchanged. Consumers
must not reverse this protection blindly or assume CSV is a lossless input format.
Markdown escapes researcher-supplied HTML, image/link syntax, pipes and headings.
URLs are displayed as source text, not used for automatic fetches or embedded media.

## Research-lane integration

This is a sibling research aid, not a replacement for the existing workshare
assessment compiler or analyst workbench. Existing research packs remain canonical
for their narratives; an adapter can map their cited statements into this schema.
Do not promote this report into a twelve-cell assessment rating or authority input.

| Research input | Suggested use here | Meaning to preserve |
|---|---|---|
| Peer cohort / software-delivery / IAM / RIS / ESS practice cards | Source plus record, with actual institution/service boundary and transfer limits | Public context does not establish Iowa's architecture, behavior or maturity. |
| Reliability metrics and service targets | Metric plus directly cited supporting record; target-only records remain `policy` or `proposal` | Targets are not observed outcomes; historical periods remain historical. |
| Framework crosswalk | `framework` record with exact version and section | Practices, outcomes and risk constructs do not become empirical maturity scales. |
| Report drafting | Use record references as contextual support; carry remaining local questions | Local findings require separately gathered and reviewed engagement evidence. |

An adapter must retain actual source locators, map evidence kinds explicitly,
leave unavailable metric fields `null`, and preserve the original research pack
as a reference. Do not invent denominators just to get an aligned label. This
package contains no adapter to private evidence or current assessment authority.

## Operating limits and validation scope

The CLI limits input to 4,000,000 bytes; the schema permits at most 1,000 sources,
1,000 records, 500 metrics and 2,000 selected candidate pairs. Automatic pair count
is checked before pair construction; larger same-key sets can use explicit pairs.
These bounds control this offline tool's work, not fleet access or resources.
Text fields are bounded to 8,000 characters. Duplicate JSON keys, nonfinite JSON
numbers, invalid UTF-8, unexpected keys and malformed references are rejected.

The direct Python API expects ordinary trusted-interpreter JSON objects. This is
not a sandbox against hostile Python objects, reflective interpreter mutation or
concurrent caller mutation. It makes no live network calls, does not inspect
applications, and does not submit, approve, invoice, schedule, deploy or contact
anyone. Local regression results do not substitute for repository-required hosted
execution and integration review.
