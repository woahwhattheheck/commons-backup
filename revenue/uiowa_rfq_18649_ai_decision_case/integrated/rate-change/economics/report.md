# AI workflow economics — modeled preparation output

**SYNTHETIC inputs; not observed University outcomes.** Horizon: 12 months; currency: USD.

Economic net values staff capacity at the stated loaded rate and subtracts external cash. Cash conversion is a separate, signed scenario assumption, not a savings forecast.

| Scenario | Economic range | Economic base | Cash-conversion base | Net capacity hours | Classification |
|---|---:|---:|---:|---:|---|
| CASE-SYN-ESS-CHANGE-MEMO | 12370.08 to 59882.00 | 32308.96 | UNKNOWN | 362.80 | POSITIVE_ACROSS_RANGE |

## CASE-SYN-ESS-CHANGE-MEMO: Drafting a service-change memo from an approved change ticket (SYNTHETIC)

Fictional effort records mapped to canonical economics. Per-document repair includes post-acceptance maintenance; recurring maintenance_hours excludes that effort.

Missing inputs (not imputed as zero): cash_conversion_fraction.

Base-assumption break-even assisted tasks/month: **2.16** (whole-task ceiling: 3.00).
Maximum checking minutes/task at base volume: **99.04**; a negative value means no nonnegative checking time can break even under these assumptions.
Simple payback months: **0.33**. Missing payback means no modeled recovery, not immediate recovery.

### Measurements that would change the decision

- **cash_conversion_fraction** (MISSING_INPUT): Document what fraction of the signed capacity value would actually change payroll or contractor cash; zero is not an automatic fact.
- **monthly_tasks** (RANGE_SENSITIVITY): Count comparable eligible tasks, including unsuccessful attempts; record period and exclusions.
- **loaded_hourly_rate** (RANGE_SENSITIVITY): Obtain an agreed aggregate loaded-labor valuation; document role mix and valuation basis.
- **baseline_minutes** (RANGE_SENSITIVITY): Time the current workflow through accepted output, not first draft, for a comparable task mix.
- **rework_minutes** (RANGE_SENSITIVITY): Measure extra repair or manual fallback time conditional on rework, without double counting author/checking time.
- **checking_minutes** (RANGE_SENSITIVITY): Time verification of every assisted output, including discarded outputs and source checks.

## Interpretation boundaries

- Independent box ranges are not probability distributions or confidence intervals.
- A single loaded rate values capacity, not individual productivity or guaranteed cash savings.
- Linear steady-state task mix, volume and costs; no discounting, seasonality, ramp or quality valuation.
- Negative capacity requires staffing feasibility assessment even when cash conversion is zero.
- Quality/usefulness evidence and acceptable outputs must be evaluated separately.

Input SHA-256: `0b359b74ed9345a7504208cf4fe9fb9b66d2a6a7a6150e7ec3be6619a221eab8`
Model SHA-256: `72b1151521a6801890ba3494a3b3b3d3f4f2997350500977eee59bea47748bea`
