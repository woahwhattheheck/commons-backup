# AI workflow economics — modeled preparation output

**SYNTHETIC inputs; not observed University outcomes.** Horizon: 12 months; currency: USD.

Economic net values staff capacity at the stated loaded rate and subtracts external cash. Cash conversion is a separate, signed scenario assumption, not a savings forecast.

| Scenario | Economic range | Economic base | Cash-conversion base | Net capacity hours | Classification |
|---|---:|---:|---:|---:|---|
| SYN-ESS-DOCS | 11996.80 to 242678.00 | 90942.00 | -858.00 | 1530.00 | POSITIVE_ACROSS_RANGE |
| SYN-RIS-REVIEW | -34116.00 to -6716.00 | -14439.00 | -924.00 | -225.25 | NEGATIVE_ACROSS_RANGE |
| SYN-IAM-SUMMARY | -32397.36 to 49873.12 | 3810.30 | -345.00 | 76.95 | SENSITIVE_TO_ASSUMPTIONS |
| SYN-ESS-UNKNOWN | UNKNOWN | UNKNOWN | UNKNOWN | UNKNOWN | UNKNOWN |

## SYN-ESS-DOCS: Fictional documentation drafting

High-volume synthetic case. Comparable accepted-output quality is an assumption to test separately. Cash conversion is explicitly zero, so positive capacity value does not claim a cash saving.

Base-assumption break-even assisted tasks/month: **12.87** (whole-task ceiling: 13.00).
Maximum checking minutes/task at base volume: **30.68**; a negative value means no nonnegative checking time can break even under these assumptions.
Simple payback months: **0.16**. Missing payback means no modeled recovery, not immediate recovery.

### Measurements that would change the decision

- **baseline_minutes** (RANGE_SENSITIVITY): Time the current workflow through accepted output, not first draft, for a comparable task mix.
- **monthly_tasks** (RANGE_SENSITIVITY): Count comparable eligible tasks, including unsuccessful attempts; record period and exclusions.
- **loaded_hourly_rate** (RANGE_SENSITIVITY): Obtain an agreed aggregate loaded-labor valuation; document role mix and valuation basis.
- **adoption_fraction** (RANGE_SENSITIVITY): Measure the fraction of eligible tasks actually attempted with the assisted workflow.
- **checking_minutes** (RANGE_SENSITIVITY): Time verification of every assisted output, including discarded outputs and source checks.
- **author_minutes** (RANGE_SENSITIVITY): Record prompting, context preparation and editing; exclude checking and rework counted below.

## SYN-RIS-REVIEW: Fictional low-volume, high-review workflow

Verification and repair dominate this synthetic task. More volume is not a cure for a negative per-task contribution. No claim is made about research staff or University practices.

Base-assumption break-even assisted tasks/month: **UNKNOWN** (whole-task ceiling: UNKNOWN).
Maximum checking minutes/task at base volume: **-81.96**; a negative value means no nonnegative checking time can break even under these assumptions.
Simple payback months: **UNKNOWN**. Missing payback means no modeled recovery, not immediate recovery.

### Measurements that would change the decision

- **loaded_hourly_rate** (RANGE_SENSITIVITY): Obtain an agreed aggregate loaded-labor valuation; document role mix and valuation basis.
- **support_hours** (RANGE_SENSITIVITY): Record recurring operational support and troubleshooting, excluding per-task rework.
- **adoption_fraction** (RANGE_SENSITIVITY): Measure the fraction of eligible tasks actually attempted with the assisted workflow.
- **monthly_tasks** (RANGE_SENSITIVITY): Count comparable eligible tasks, including unsuccessful attempts; record period and exclusions.
- **maintenance_hours** (RANGE_SENSITIVITY): Record recurring updates, evaluation refresh and knowledge maintenance, excluding support.
- **checking_minutes** (RANGE_SENSITIVITY): Time verification of every assisted output, including discarded outputs and source checks.

## SYN-IAM-SUMMARY: Fictional requirements summarization

Independent synthetic ranges intentionally span both signs of net value. The base case is not a prediction, median, percentile or promised productivity multiplier.

Base-assumption break-even assisted tasks/month: **38.90** (whole-task ceiling: 39.00).
Maximum checking minutes/task at base volume: **20.04**; a negative value means no nonnegative checking time can break even under these assumptions.
Simple payback months: **2.93**. Missing payback means no modeled recovery, not immediate recovery.

### Measurements that would change the decision

- **baseline_minutes** (RANGE_SENSITIVITY): Time the current workflow through accepted output, not first draft, for a comparable task mix.
- **checking_minutes** (RANGE_SENSITIVITY): Time verification of every assisted output, including discarded outputs and source checks.
- **monthly_tasks** (RANGE_SENSITIVITY): Count comparable eligible tasks, including unsuccessful attempts; record period and exclusions.
- **adoption_fraction** (RANGE_SENSITIVITY): Measure the fraction of eligible tasks actually attempted with the assisted workflow.
- **author_minutes** (RANGE_SENSITIVITY): Record prompting, context preparation and editing; exclude checking and rework counted below.
- **rework_fraction** (RANGE_SENSITIVITY): Count tasks requiring additional repair after ordinary checking; retain failed and abandoned tasks.

## SYN-ESS-UNKNOWN: Fictional test drafting with missing verification evidence

Checking and rework incidence are deliberately unmeasured. Generation speed alone cannot support a net-value result. Null is unknown, never zero.

Missing inputs (not imputed as zero): checking_minutes, rework_fraction.

### Measurements that would change the decision

- **checking_minutes** (MISSING_INPUT): Time verification of every assisted output, including discarded outputs and source checks.
- **rework_fraction** (MISSING_INPUT): Count tasks requiring additional repair after ordinary checking; retain failed and abandoned tasks.

## Interpretation boundaries

- Independent box ranges are not probability distributions or confidence intervals.
- A single loaded rate values capacity, not individual productivity or guaranteed cash savings.
- Linear steady-state task mix, volume and costs; no discounting, seasonality, ramp or quality valuation.
- Negative capacity requires staffing feasibility assessment even when cash conversion is zero.
- Quality/usefulness evidence and acceptable outputs must be evaluated separately.

Input SHA-256: `65119662daab52d6b4d84ddc4da2fb523d6b2a0ad7f13cf33655bd7350975ab2`
Model SHA-256: `72b1151521a6801890ba3494a3b3b3d3f4f2997350500977eee59bea47748bea`
