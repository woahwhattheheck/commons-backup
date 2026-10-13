# UIOWA-046: Test reliability and feedback latency

An offline, dependency-free analysis kit for exported test-attempt metadata. It
helps an assessor ask better questions about unreliable test signals, repeated
reruns, runner queues, and slow feedback. It does not rate a team, diagnose a
product defect, validate a release, or establish University practices.

**All supplied examples are fictional.** ESS, RIS, and IAM are assessment-group
labels, not claims about their actual systems. The fixture names, revisions,
services, timestamps, incidents, and triage references are invented. This is
internal assessment preparation, not a customer delivery or University submission.

## Run the complete example

From the repository root with Python 3.10 or newer:

```sh
python revenue/uiowa_rfq_18649_test_reliability/analyze.py \
  revenue/uiowa_rfq_18649_test_reliability/synthetic_runs.csv \
  --synthetic --format markdown
python revenue/uiowa_rfq_18649_test_reliability/analyze.py \
  revenue/uiowa_rfq_18649_test_reliability/synthetic_runs.csv \
  --synthetic --format json > /tmp/test-reliability.json
python -m unittest discover \
  -s revenue/uiowa_rfq_18649_test_reliability -p 'test_*.py' -v
```

The CLI only reads the selected input and writes its report to standard output.
It makes no network requests, executes no supplied commands, does not modify
source files, and does not schedule or cancel tests. Structural errors return
exit status 2 with no partial report. Missing or invalid timestamps preserve the
outcome and generate data-quality questions rather than rejecting the whole file.
The output contains the SHA-256 of the exact input bytes. Repeating the same
input, thresholds, format, and synthetic flag produces the same output.

## CSV contract

`template.csv` provides the exact header. Column order can change, but no column
may be omitted, repeated, or added. Use UTF-8 CSV; a byte-order mark is accepted.
Standard CSV quoting supports commas and line breaks in source references.
Leading and trailing cell whitespace is stripped. Blank rows are ignored.

| Column | Required value and interpretation |
|---|---|
| `run_id` | Nonempty logical execution identifier; all attempts of one test execution share it. |
| `group` | Nonempty assessment grouping; no fixed set or implied institutional boundary. |
| `service` | Nonempty service scope; separates identical run IDs across services. |
| `test_id` | Nonempty stable test identity, including parameters/shard identity where needed. |
| `revision` | Exact source revision; blank is retained as unknown and prevents a comparable retry classification. |
| `environment` | Comparable runner/environment fingerprint; blank or changed values prevent a comparable retry classification. |
| `data_version` | Test-data/dependency-input fingerprint; blank or changed values prevent a comparable retry classification. |
| `attempt` | Positive ASCII integer, starting at 1 within a complete logical chain. Missing attempts are diagnosed, never fabricated. |
| `outcome` | Exactly `pass`, `fail`, `error`, `skipped`, or `cancelled`. |
| `failure_kind` | Empty, `test`, `infrastructure`, or `unknown`; failure fields are permitted only for `fail` or `error`. |
| `failure_signature` | Optional normalized failure fingerprint. Required to identify repeated same-signature test failures. Do not include secrets or raw sensitive logs. |
| `queued_at` | Timezone-aware ISO 8601 timestamp or blank. |
| `started_at` | Timezone-aware ISO 8601 timestamp or blank. |
| `finished_at` | Timezone-aware ISO 8601 timestamp or blank. |
| `triage` | Blank/`unreviewed`, `confirmed_flaky`, `confirmed_defect`, or `confirmed_infrastructure`. This is a supplied diagnosis, not one made by the calculator. |
| `triage_ref` | Nonempty supporting reference whenever triage is confirmed. A reference's presence is not verification of its contents. |
| `source_ref` | Nonempty original observation locator; an opaque ID or source URL is acceptable. It is retained, not fetched. |

The unique attempt key is `(group, service, run_id, test_id, attempt)`. Duplicate
attempts are rejected instead of silently double-counted, including `01` versus
`1`. A provider that changes its job ID on every retry needs an adapter to map
those jobs to one logical `run_id`; do not group unrelated runs just because
names match. The adapter must retain environment and test-data fingerprints, or
leave them unknown rather than inventing comparability.

## Observation is not diagnosis

The JSON report retains **both** `observed_pattern` and `reported_triage`.

| Observed pattern | What it establishes and what it does not |
|---|---|
| `first_pass` | One exported attempt numbered 1 passed. It does not establish complete export coverage. |
| `passes_with_extra_attempts` | Multiple exported attempts all passed; ask why they were rerun or whether a failure was omitted. |
| `retry_recovered_unconfirmed` | A contiguous, comparable, test-failure chain started with failure and ended with pass. This is a recovery candidate, not confirmed flakiness or a fix. |
| `repeated_test_failure_unconfirmed` | At least two comparable failures share a nonempty signature. A product defect, deterministic test defect, or other cause still needs controlled evidence. |
| `infrastructure_or_execution_error` | An explicit infrastructure label or `error` outcome exists. An `error` may be test setup, not infrastructure; the question preserves that distinction. |
| `unresolved_failure` | A failure exists, but context, chronology, signature, or outcome sequence does not support a more specific pattern. |
| `incomplete_execution` | Missing initial history or a non-executed outcome prevents ordinary completion interpretation. |

A comparable chain has attempts exactly `1..N`, one nonempty revision,
environment, and data version, and no observed overlap between retries.
Matching fingerprints are only the exporter's comparability claim. Unrecorded
runner/dependency changes can still explain recovery. An isolated passing rerun
is insufficient evidence of the cause of the preceding failure.

Conflicting supplied triage decisions remain `conflicting`; all references
survive for review. Confirmed diagnoses require a reference but are never
independently certified. A changed triage decision needs reconciliation in the
upstream record, not silent last-write-wins here.

## Metrics and denominators

Every rate contains `numerator`, `denominator`, and `fraction`; an empty
denominator produces `null`, not 0. Per-service summaries are recomputed from
observations, not averaged from other percentages.

- **First-attempt failure rate:** fail/error initial attempts divided by logical
  chains with an exported attempt 1 in pass/fail/error. Missing attempt 1 and
  cancelled/skipped initial attempts are excluded.
- **Observed final-pass rate:** chains whose highest exported attempt passed,
  divided by chains whose highest exported attempt is pass/fail/error. This can
  include incomplete histories; it is intentionally not a release-success rate.
- **Observed test-retry recovery rate:** comparable test-failure chains that end
  in pass divided by comparable chains starting with a known test failure. The
  denominator includes failures with no exported rerun. It describes this export,
  not population flakiness prevalence or the success of a retry policy.

Latencies are seconds, with explicit `eligible_count`, `observed_count`, and
`unavailable_count`. A genuine zero duration is retained. Nulls are not imputed.
`total_observed_seconds` sums known samples only and is not an estimate for
missing samples. It is not wall-clock elapsed time across parallel jobs.

| Metric | Unit and eligibility |
|---|---|
| `queue` | Started minus queued, per pass/fail/error attempt. |
| `execution` | Finished minus started, per pass/fail/error attempt. |
| `logical_feedback` | Last finished minus initial queued, once per complete chain ending in pass/fail/error, with valid endpoints and consistent observed clocks. Includes between-retry waiting. |
| `retry_execution` | Execution time for exported pass/fail/error attempts numbered above 1. This measures observed rerun compute time, not monetary cost or avoidable waste. |

A reversed timestamp invalidates all duration pairs on that row. Overlapping
retries invalidate chain comparability and logical feedback. Missing timestamps
invalidate only affected pairs; an unknown queue timestamp can coexist with a
known execution duration. A terminal cancelled/skipped attempt censors logical
feedback. The min/max observed timestamps are bounds of available timestamps,
not a claim that all runs in that period were exported.

`p50` is the sample median; `p95` is nearest rank (`ceil(0.95*n)`). In a small
sample the p95 may simply be the maximum. These are descriptive values, not
service-level objectives, confidence intervals, industry benchmarks, or evidence
that differently sampled groups are comparable.

## Investigation priorities

Priority 1 addresses reported defects/infrastructure incidents, contradictory
triage, repeated same-signature failures, and unresolved failures. Priority 2
addresses retry-recovery diagnosis, reported flakiness, evidence quality, and
latency triggers. Priority 3 asks about unexplained passing reruns and incomplete
execution. Within a priority, larger observed time impact comes first, then a
stable identity ordering. This is a transparent default review order, not a
severity rating, employee score, causal model, or approved remediation backlog.

The queue and feedback triggers default to **300** and **1800** seconds:

```sh
python revenue/uiowa_rfq_18649_test_reliability/analyze.py export.csv \
  --queue-threshold 120 --feedback-threshold 900 --format markdown
```

These numbers are editable investigation assumptions only. Establish locally
appropriate expectations and service criticality with the responsible team.
Never infer a service breach or insufficient maturity from the defaults.

## Worked synthetic expectations

The fixture contains 18 attempts in 12 logical chains across three fictional
services. It deliberately mixes repeatable assertion failures, an externally
triaged defect, confirmed and unreviewed retry recovery, an execution incident,
changed data, incomplete history, cancellation, a slow queue, and missing or
reversed clocks. `SYNTHETIC_REPORT.md` is the generated readable result.

| Quantity | Expected synthetic result |
|---|---:|
| Initial failures / eligible initial attempts | 6 / 10 |
| Observed terminal passes / executed terminal chains | 9 / 11 |
| Comparable test-failure recoveries / eligible chains | 2 / 4 |
| Queue durations observed / eligible | 15 / 17 |
| Execution durations observed / eligible | 16 / 17 |
| Logical feedback durations observed / eligible | 8 / 12 |
| Observed retry execution | 140 seconds across 7 exported attempts |
| Queue p95 / logical-feedback p95 | 1200 / 2700 seconds |

The final-pass fraction can look healthy while many initial attempts fail, but
these fractions have **different denominators**. Investigate the underlying
chains rather than subtracting the percentages as a causal estimate. The example
supports no conclusion about the University or a real delivery organization.

## Reuse in the assessment workflow

The JSON schema identifier is `tjlabs-test-reliability/v1`. Its top-level fields
are `schema`, `synthetic`, `authority`, `coverage`, `thresholds_seconds`,
`summary`, `by_service`, `cohorts`, `investigations`, `row_issues`, and (through
the CLI) `input_sha256`. Register the supplied export as evidence; cite a
cohort's `source_refs` and triage references in a finding, not just an aggregate
percentage. The original export hash and analysis settings should accompany
any retained report. Keep the synthetic flag with downstream artifacts.

This additive tool does not change the existing workshare compiler, maturity
ratings, twelve-cell assessment matrix, or workbench. A future provider adapter
should prove retry identity, outcome mapping, clock semantics, coverage window,
and source locator preservation before importing native exports. Do not send
private logs to public repositories or paste credentials into the CSV.
