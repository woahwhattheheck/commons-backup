# AI workflow economics — modeled preparation output

**SYNTHETIC inputs; not observed University outcomes.** Horizon: 12 months; currency: USD.

Economic net values staff capacity at the stated loaded rate and subtracts external cash. Cash conversion is a separate, signed scenario assumption, not a savings forecast.

| Scenario | Economic range | Economic base | Cash-conversion base | Net capacity hours | Classification |
|---|---:|---:|---:|---:|---|
| CASE-SYN-IAM-RUNBOOK | UNKNOWN | UNKNOWN | UNKNOWN | UNKNOWN | UNKNOWN |

## CASE-SYN-IAM-RUNBOOK: Producing an access-review runbook section (SYNTHETIC)

Fictional effort records mapped to canonical economics. Per-document repair includes post-acceptance maintenance; recurring maintenance_hours excludes that effort.

Missing inputs (not imputed as zero): author_minutes, checking_minutes, rework_fraction, rework_minutes, cash_conversion_fraction.

### Measurements that would change the decision

- **author_minutes** (MISSING_INPUT): Record prompting, context preparation and editing; exclude checking and rework counted below.
- **checking_minutes** (MISSING_INPUT): Time verification of every assisted output, including discarded outputs and source checks.
- **rework_fraction** (MISSING_INPUT): Count tasks requiring additional repair after ordinary checking; retain failed and abandoned tasks.
- **rework_minutes** (MISSING_INPUT): Measure extra repair or manual fallback time conditional on rework, without double counting author/checking time.
- **cash_conversion_fraction** (MISSING_INPUT): Document what fraction of the signed capacity value would actually change payroll or contractor cash; zero is not an automatic fact.

## Interpretation boundaries

- Independent box ranges are not probability distributions or confidence intervals.
- A single loaded rate values capacity, not individual productivity or guaranteed cash savings.
- Linear steady-state task mix, volume and costs; no discounting, seasonality, ramp or quality valuation.
- Negative capacity requires staffing feasibility assessment even when cash conversion is zero.
- Quality/usefulness evidence and acceptable outputs must be evaluated separately.

Input SHA-256: `0cae1e220eeb7bc13a3c1a889ac76e81bffcc94a81fbdf15c14dc79eb5b6cbb3`
Model SHA-256: `72b1151521a6801890ba3494a3b3b3d3f4f2997350500977eee59bea47748bea`
