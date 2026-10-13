# UIOWA-064 — interpretation notes and verified synthetic example

Status: **assessment preparation / synthetic only**  
Owner: ZZ-Semaphore / GPT-5.6 Sol

## Source register

1. DORA, "DORA's software delivery performance metrics"  
   https://dora.dev/guides/dora-metrics/  
   Last updated 2026-01-05; accessed 2026-09-19.

2. DORA, "A history of DORA's software delivery metrics"  
   https://dora.dev/insights/dora-metrics-history/  
   Published / last updated 2026-01-02; accessed 2026-09-19.

The current guide states that DORA now uses five software-delivery performance metrics: three throughput measures (change lead time, deployment frequency, failed deployment recovery time) and two instability measures (change fail rate, deployment rework rate). The history page documents the change from the older four-metric model, including the narrowed failed-deployment recovery concept and the addition of deployment rework rate.

## How to run the synthetic example

From this directory:

```bash
python calculator.py fixtures/synthetic_deployments.csv \
  --window-start 2026-09-01T00:00:00Z \
  --window-end 2026-09-15T00:00:00Z
```

The fixture contains eight fictional production deployment events for one fictional service, `synthetic-registration`. It is not University of Iowa evidence.

## Verified expected output

The exact fixture and observation window above produce:

| Metric | Expected synthetic result | Coverage |
|---|---:|---|
| Change lead time | median 11.0 h; mean 14.875 h | COMPLETE, 8/8 |
| Deployment frequency | 8 deployments / 14 days = 4.0 per week | COMPLETE, 8/8 |
| Median interdeployment interval | 46.0 h | COMPLETE |
| Failed deployment recovery time | median 3.0 h; mean 3.0 h | COMPLETE, 2/2 failed deployments |
| Change fail rate | 2 / 8 = 25.0% | COMPLETE |
| Deployment rework rate | 2 / 8 = 25.0% | COMPLETE |

Local regression verification for the published bytes also exercises:

- multiple services without an explicit service filter are rejected;
- missing commit linkage makes lead-time coverage PARTIAL rather than imputing a duration;
- a failed deployment without recovery time makes recovery coverage PARTIAL;
- unknown failure/rework classifications make their rate coverage PARTIAL;
- impossible commit-after-deployment chronology is rejected.

## Interpretation rules

### 1. Measure one service/application context at a time

DORA's current guide says the metrics are best applied at the application or service level and cautions that comparisons across very different applications can be misleading. The calculator enforces this by refusing mixed-service input unless the operator selects one service.

Do not combine ESS, RIS, and IAM service data into one number merely because the source rows share columns.

### 2. Do not invent peer percentiles

This instrument calculates observed values only. It does not map them to an invented "top quartile", "high performer", percentile, or maturity tier. Any external benchmark comparison would need a separately sourced, methodologically comparable cohort and measurement definition.

### 3. Do not use the metrics as individual productivity ratings

The unit of interpretation is the service delivery system, not an employee. The current DORA guide emphasizes shared delivery ownership and warns about competition and gaming. These outputs must not be used to score individual developers, operators, release engineers, or managers.

### 4. Do not hide missing data

Unknown linkage, failure classification, recovery timestamps, or rework classification remains unknown. The report exposes coverage alongside every affected metric.

A PARTIAL 10% rate does not mean "10% with high confidence"; it means the numerator/denominator were calculated from only the rows whose classification was known. Review the coverage fields before interpreting the rate.

### 5. A missing qualifying event is not zero duration

If no failed deployments were observed, recovery time is `NOT_OBSERVED`, not zero. Zero would incorrectly imply an observed instantaneous recovery.

### 6. Preserve denominator semantics

For this tool:

- change fail rate denominator = deployments with known `intervention_required`;
- deployment rework rate denominator = deployments with known `unplanned_rework`;
- recovery-time denominator = qualifying failed deployments;
- lead-time denominator = deployments with known change/deployment linkage.

If the engagement chooses a different denominator or event model, record that change before comparing periods.

### 7. Treat collection mechanics as part of the evidence

A precise-looking number can still have weak evidence. For each real metric extract, record:

- service boundary;
- observation window;
- source systems;
- deployment event definition;
- change-to-deployment linkage rule;
- failure/intervention classification rule;
- recovery endpoint definition;
- rework classification rule;
- missing-data count;
- known source exclusions.

This allows the assessment to distinguish an operational result from a data-quality limitation.

## Bounded recovery follow-up

Deployment selection uses `[window_start, window_end)`. Recovery follow-up is a separate, inclusive endpoint. Pass `--recovery-observed-through` with an offset-bearing timestamp at or after `--window-end` to exclude later recoveries from the summary. The Python `calculate()` API accepts the same option as an aware `datetime`. All timestamps, including the cutoff, normalize to UTC before comparison.

```bash
python calculator.py fixtures/synthetic_deployments.csv \
  --window-start 2026-09-01T00:00:00Z \
  --window-end 2026-09-08T13:00:00Z \
  --recovery-observed-through 2026-09-08T13:00:00Z \
  --output recovery-report.json
```

This selects five existing fictional deployments. `DEP-002` supplies the only recovery duration available by the cutoff: 4 hours. `DEP-005` recovered at 14:00, after the 13:00 cutoff, so it remains a qualifying failure but is excluded from recovery statistics. Recovery coverage is `PARTIAL`, with two eligible failures, one used and one missing at the cutoff; no zero duration is substituted. The report's recovery `evidence` separates observed recovery IDs, missing timestamps, recoveries after the cutoff, and unknown failure classifications.

Omitting the option preserves the previous arithmetic over all supplied recovery records and labels the scope `ALL_SUPPLIED_RECORDS_RETROSPECTIVE`. An explicit cutoff labels it `EXPLICIT_RECOVERY_CUTOFF`; a recovery exactly at that cutoff is included. Unknown failure classification keeps recovery coverage partial, even when every known failure has a recovery timestamp.

A timestamp filter is not historical source verification. The report does not prove when failure/rework classifications became known, whether a record was actually available at the cutoff, or whether the source export was complete. `classification_as_of_verified` and `source_export_completeness_verified` remain false. Recovery mean and median describe observed cases only; unresolved or slower recoveries can bias those statistics.

## Missing-classification bounds

The existing `rate` and `percent` still use only known classifications. Their `denominator_basis` is explicitly `KNOWN_CLASSIFICATION_ONLY`. Alongside them, `full_cohort_rate_bounds` shows the logical range if every unknown classification were negative versus positive: `positive / total` through `(positive + unknown) / total`, rounded to six decimal places. The population is the selected deployment cohort; bounds use proportions, not percentages.

These are not confidence intervals, peer benchmarks or imputed rates. For example, one known failure, one known non-failure and two unclassified deployments give a known-only rate of 50%, but full-cohort bounds of 25% through 75%. An entirely unclassified cohort retains a null known-only rate and bounds of 0 through 1. Existing empty-selection errors remain unchanged.

## Recommended assessment use

Use these metrics as one evidence stream alongside interviews, delivery-flow traces, release/recovery records, and service context. Trend the same service over consistently defined windows where possible. When a metric changes materially, use it to generate investigation questions rather than assuming a cause.

Examples:

- Lead time rises while deployment frequency falls: inspect queueing, review, packaging, or environment wait evidence before attributing cause.
- Change fail rate rises while recovery time stays stable: inspect release composition, test coverage, rollback mechanics, and incident classification.
- Rework rate rises: check whether incident-driven deployments actually increased or whether classification practices changed.
- All five improve: verify that the event model and coverage stayed stable before interpreting the movement as process improvement.

## Non-authority boundary

This synthetic calculator does not establish University performance, compliance, maturity, procurement suitability, staffing quality, or contract acceptance. It performs deterministic arithmetic over supplied records and makes its coverage/interpretation limits explicit.
