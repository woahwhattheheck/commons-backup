# AI workflow economics — modeled preparation output

**SYNTHETIC inputs; not observed University outcomes.** Horizon: 12 months; currency: USD.

Economic net values staff capacity at the stated loaded rate and subtracts external cash. Cash conversion is a separate, signed scenario assumption, not a savings forecast.

| Scenario | Economic range | Economic base | Cash-conversion base | Net capacity hours | Classification |
|---|---:|---:|---:|---:|---|
| CASE-SYN-RIS-VENDOR-SUMMARY | -30283.20 to -1430.80 | -8775.04 | UNKNOWN | -99.20 | NEGATIVE_ACROSS_RANGE |

## CASE-SYN-RIS-VENDOR-SUMMARY: Summarising a third-party vendor security questionnaire (SYNTHETIC)

Fictional effort records mapped to canonical economics. Per-document repair includes post-acceptance maintenance; recurring maintenance_hours excludes that effort.

Missing inputs (not imputed as zero): cash_conversion_fraction.

Base-assumption break-even assisted tasks/month: **UNKNOWN** (whole-task ceiling: UNKNOWN).
Maximum checking minutes/task at base volume: **25.24**; a negative value means no nonnegative checking time can break even under these assumptions.
Simple payback months: **UNKNOWN**. Missing payback means no modeled recovery, not immediate recovery.

### Measurements that would change the decision

- **cash_conversion_fraction** (MISSING_INPUT): Document what fraction of the signed capacity value would actually change payroll or contractor cash; zero is not an automatic fact.
- **rework_minutes** (RANGE_SENSITIVITY): Measure extra repair or manual fallback time conditional on rework, without double counting author/checking time.
- **loaded_hourly_rate** (RANGE_SENSITIVITY): Obtain an agreed aggregate loaded-labor valuation; document role mix and valuation basis.
- **monthly_tasks** (RANGE_SENSITIVITY): Count comparable eligible tasks, including unsuccessful attempts; record period and exclusions.
- **baseline_minutes** (RANGE_SENSITIVITY): Time the current workflow through accepted output, not first draft, for a comparable task mix.
- **checking_minutes** (RANGE_SENSITIVITY): Time verification of every assisted output, including discarded outputs and source checks.

## Interpretation boundaries

- Independent box ranges are not probability distributions or confidence intervals.
- A single loaded rate values capacity, not individual productivity or guaranteed cash savings.
- Linear steady-state task mix, volume and costs; no discounting, seasonality, ramp or quality valuation.
- Negative capacity requires staffing feasibility assessment even when cash conversion is zero.
- Quality/usefulness evidence and acceptable outputs must be evaluated separately.

Input SHA-256: `fac1cc3636c9dd6c3430f3325cb9c893545662bfaa8fd81b05c2b4207cd8eada`
Model SHA-256: `72b1151521a6801890ba3494a3b3b3d3f4f2997350500977eee59bea47748bea`
