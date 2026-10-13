# SEC Facts Vintage

An offline data-engineering toolkit for comparing exactly specified financial facts across retained SEC filing observations. It produces an inspectable JSON/CSV/HTML bundle rather than guessing which number a researcher meant.

**This is not an investment recommendation, a restatement detector, an accounting-policy engine, or a source-authentication service.** It performs no network requests, trades, filings, outreach, or account mutations. The supplied demonstration is entirely synthetic.

## Run the complete demonstration

Python 3.10+ and the standard library are sufficient; validation here used Python 3.13.5 on a cloud Linux runtime. No package installation or credentials are needed.

```sh
cd revenue/sec-facts-vintage
python sec_facts_vintage.py inventory --source examples/companyfacts.synthetic.json
python sec_facts_vintage.py compile \
  --source examples/companyfacts.synthetic.json \
  --plan examples/plan.synthetic.json \
  --bundle /tmp/sec-facts-review-NEW
python sec_facts_vintage.py verify \
  --source examples/companyfacts.synthetic.json \
  --plan examples/plan.synthetic.json \
  --bundle /tmp/sec-facts-review-NEW
```

Use a new directory name for each compilation. Existing output is never overwritten. Open `review.html` locally; it has no remote assets, scripts, analytics, external forms, or network dependency. `inventory` lists available taxonomy/concept/unit combinations in the supplied snapshot; it does not select mappings for you.

The six-query example produces three `CHANGED` results, one `AMBIGUOUS_LATEST`, and two `NO_ELIGIBLE_FACT` results. In particular, a six-month YTD revenue observation is **not** silently treated as the second quarter, a later filing beyond the cutoff does **not** replace the earlier value, and two different observations filed on the same date do **not** acquire an invented chronological order.

## Compile a multi-company handoff

`batch.py` runs the same compiler for an explicit list of retained source/plan pairs. It writes each unchanged native four-file bundle under `companies/<job-id>/`, plus a combined CSV, an HTML index linking to every company review, a machine-readable `batch.json` summary, and a final batch manifest. All query outcomes remain visible, including missing, ambiguous and conflicted results. Outcome counts are query counts; financial values are never added across companies, currencies or plans.

Save a job manifest beside your retained files, for example:

```json
{
  "schema": "sec-facts-vintage-batch/v1",
  "jobs": [
    {"id": "company-a", "source": "company-a.json", "plan": "company-a.plan.json"},
    {"id": "company-b", "source": "company-b.json", "plan": "company-b.plan.json"}
  ]
}
```

These are example filenames, not supplied issuer records. Each plan has the existing extraction-plan schema below and explicitly chooses that source's CIK, concepts, units, actual periods, forms and filing cutoff. Relative input paths resolve from the job manifest's directory, regardless of the shell's working directory; absolute paths also work. The batch does not download files, generate mappings or select a common cutoff. A company may appear in several distinctly named jobs when the operator explicitly wants different retained sources or plans.

From the repository root:

```sh
python revenue/sec-facts-vintage/batch.py compile \
  --batch /path/retained/jobs.json --bundle /path/new-batch-review
python revenue/sec-facts-vintage/batch.py verify \
  --batch /path/retained/jobs.json --bundle /path/new-batch-review
```

Open the top-level `review.html` for the complete outcome table and company links. `review.csv` prepends `job_id` to the native CSV columns while preserving decimal strings and spreadsheet text protection. `batch.json` records every job's CIK, cutoff, forms, query count, status counts, source/plan digests and native manifest digest. The batch manifest binds all index files and each native company manifest. Local input paths are not copied into these reports.

Keep the exact job manifest and original source/plan files with the delivery: the generated bundle does **not** embed those originals. Relocating the entire retained-input folder preserves relative paths. Changing even whitespace in a retained input changes its digest. To replay, `verify` reads those original files, recompiles every native bundle and index, and compares every output byte. Missing or extra files/directories, altered company reviews and altered indexes fail with exit `2`; hashes alone cannot make an edited report valid. Each company bundle also remains independently usable with the existing single-company `verify` command.

All jobs are compiled before a new output directory is created, so an invalid later job produces no partial new delivery. Existing output directories are never overwritten. Publication uses the native exclusive-write behavior, writes the batch manifest last and reads back all members before returning success. An interrupted or failed filesystem write can leave an incomplete directory; keep it for inspection and use a new name for the next compilation. Trusted, stable parent directories are required, as for the single-company tool.

Batch limits are 256 KiB of job-manifest JSON, 1–100 jobs and 256 MiB of total rendered output; the existing source/plan/history limits apply to every job. IDs use 1–64 ASCII letters, digits, hyphens or underscores, begin with a letter or digit, and must be unique even when letter case is ignored. Jobs and queries are rendered in deterministic ID order. `compile --require-unambiguous` still publishes and verifies every review, then returns `3` if any query is missing, ambiguous or conflicted. Ordinary successful compile/verify returns `0`; malformed input, I/O and replay failures return `2` with an error message. A current public SEC download remains a current retained observation, not a historical intraday archive.

## Extraction plan

```json
{
  "schema": "sec-facts-vintage-plan/v1",
  "cik": "0000123456",
  "filed_on_or_before": "2024-06-30",
  "forms": ["10-Q", "10-Q/A", "10-K", "10-K/A"],
  "queries": [{
    "id": "my-explicit-metric",
    "taxonomy": "us-gaap",
    "concept": "RevenueFromContractWithCustomerExcludingAssessedTax",
    "unit": "USD",
    "start": "2024-01-01",
    "end": "2024-03-31"
  }]
}
```

The example CIK is illustrative, not an assertion about an issuer. Supply the exact CIK of your retained file. `start: null` requests an instant; a one-day duration is not equivalent. Start and end dates are exact, including non-calendar fiscal periods. Filing-date cutoff is inclusive. Forms are explicit: an amendment is included only when its form is present. Fiscal-year, fiscal-period and frame labels are retained as provenance but are never substitutes for actual dates.

No concept-name fallback, unit conversion, automatic quarterly subtraction, sign reinterpretation, scale guessing, dimensional aggregation, or accounting classification is performed. Repeated query IDs and duplicate extraction scopes with new labels are rejected. Multiple periods for the same concept/unit share a parsed history index.

## Result meanings

| Status | Interpretation |
| --- | --- |
| `SINGLE_VINTAGE` | One eligible filing-date group with one unambiguous value. |
| `UNCHANGED` | Earliest and latest eligible groups have the same value. |
| `CHANGED` | The exact earliest-to-latest difference is nonzero. This does not diagnose its cause. |
| `AMBIGUOUS_LATEST` | Latest filing date contains different values; latest value and change remain null. |
| `AMBIGUOUS_BASELINE` | Earliest date contains different values; latest may be known, but first value and change remain null. |
| `SOURCE_CONFLICT` | One accession has conflicting values, filing dates or forms, or a selected fact is filed before its reported period ends. No selected value is released. |
| `NO_ELIGIBLE_FACT` | No exact-period fact survives the explicit form and filing-date filter. Missing is null/blank, never zero. |

`first_observed_filed` means the earliest date **in the supplied eligible records**, not proven first publication. All eligible observations are retained in `vintages`. Exact replay rows collapse with a count. Different accessions reporting the same value remain visible; accession order is only a deterministic presentation order, not an intraday time ordering.

Financial values are canonical decimal strings in JSON and exact decimal columns in CSV. Arithmetic uses an isolated high-precision decimal context. Scientific notation is expanded without converting through binary floats. Negative financial values remain numeric. Text fields receive spreadsheet-formula protection; all variable HTML content is escaped.

## What verification establishes

The bundle contains `report.json`, `review.csv`, `review.html`, and `manifest.json`. Its manifest records member SHA-256 values and the exact raw source/plan digests. `verify` recompiles every member from those supplied source/plan bytes and compares exact output bytes. Rehashing a manipulated report is insufficient. Missing members, extra members, changed renderings, and source/plan transplants are rejected.

The engine is deterministic for identical input bytes. Reordering source observations does not change selected results, but it **does** change the raw-source hash and therefore the integrity-bound artifact. This distinction is intentional. Raw bytes are never claimed order-invariant.

Hashes establish local byte identity, **not** SEC provenance, completeness, a valid accounting interpretation, or accurate filing content. Supply retained authoritative records and perform appropriate source review independently. The tool does not create a trusted timestamp or authenticate an historical snapshot.

## SEC coverage and temporal limitations

The [SEC API documentation](https://www.sec.gov/search-filings/edgar-application-programming-interfaces) describes Company Facts as aggregating non-custom taxonomy facts applying to the entire entity. Consequently, a missing tag here cannot establish the absence of a custom or dimensional disclosure. The same documentation explains that calendar frames may contain differing actual start/end dates and that dissemination/processing is not instantaneous.

This toolkit filters `filed` **dates**, not filing acceptance timestamps, dissemination times or actual data-vendor availability. A currently downloaded file with a historical date cutoff is not proof of the precise information available at a past intraday instant, nor of an unmodified complete historical dataset. Do not advertise backtest look-ahead elimination beyond the explicit filing-date filter. The full filing remains the interpretive source; this toolkit does not replace it.

Input structure is the retained Company Facts JSON shape: root `cik`, `entityName`, and `facts`; then taxonomy → concept → `units` → observation array. Selected observation fields are `end`, `val`, `accn`, `form`, `filed`, with optional `start`, `fy`, `fp`, `frame`. SEC records may explicitly set optional `fy` and `fp` to null; those values remain unknown provenance in the report, not invented fiscal labels. Non-null fiscal labels retain their type and range checks. Unsupported selected observation fields fail explicitly. Unrequested concept content is not semantically validated. A future SEC schema change may require a reviewed adapter.

## Resource and file boundaries

Inputs must be strict UTF-8 JSON. Duplicate object keys, nonfinite numbers, surrogate escapes, unknown plan fields, bool-as-integer aliases, invalid dates and accession shapes, reversed periods, and malformed selected records are rejected. Limits: 64 MiB source, 256 KiB plan, 256 queries, 250,000 combined records across requested concept/unit histories, 32 JSON nesting levels, two million JSON nodes, and 64 MiB rendered bundle. Source numeric values admit up to 96 significant digits and exponents from -40 to 40; computed differences allow the additional exact carry/digit span.

Use ordinary files in **trusted, stable, owner-controlled parent directories**. Final-component symlinks/non-regular files and detectable read mutation are refused. The tool is not a sandbox against a hostile same-UID process or concurrently replaced ancestor directories. New output directories are private, files are created exclusively, and the manifest is written last. Interrupted publication remains incomplete and is never deleted automatically. Verification is required before consuming output. Never treat a stranded directory as complete merely because some files exist.

Exit codes: `0` = operation succeeded; `2` = input/I/O/verification error. `compile --require-unambiguous` still publishes the review bundle but returns `3` when a query is missing, ambiguous or conflicted. A normal compile exit of zero does not mean every query has a value.

## Commercial handoff — proposed, not sold

A concrete route to revenue is a **paid financial-data QA and integration pilot**, not charging for access to free public data. Internal pricing hypothesis: **USD 4,500 fixed**, subject to buyer qualification and an approved scope. This is not an approved quote, customer commitment, receivable, savings estimate or recognized revenue.

Candidate scope: one research/data team; up to ten CIKs, twelve exact periods and twenty explicitly mapped metrics per CIK; supplied retained standard Company Facts files; one reviewed mapping plan; per-company exception bundles; a machine-readable consolidated handoff; and a documented sample of manual source checks. Proposed delivery target is five business days after complete agreed inputs, not a present commitment.

Acceptance requires the buyer to approve the concept/unit/period mapping, provide an expected comparison sample, and resolve the exceptions they choose to use. Missing/custom/dimensional disclosures, live connectors, quarter derivations, complete point-in-time archives, audit opinions and trading signals are outside this implementation. The batch command supplies the consolidated multi-company handoff while preserving those explicit mappings and each native exception review.

Before outreach, the swarm must establish the buyer's actual problem, confirm no conflicting offer, obtain Muse single-writer adjudication and applicable owner approval, and use an approved standalone non-GitHub customer surface. GitHub/Commons links are internal evidence only. This change sends nothing and asserts no commercial outcome.

## Maintenance

`VALIDATION.md` records the original local proof and its limits. After source changes, run the affected actual inventory/compile/verify commands on retained input and inspect their exit codes and reports. Preserve the distinction between reported changes, source conflicts, absent coverage and investment conclusions. Do not weaken explicit ambiguity just to populate an output table. The batch handoff continues the original #15847/#15872 operation and reuses its compiler and comparison rules; the fiscal-label compatibility change preserves explicit unknown labels from retained SEC records.
