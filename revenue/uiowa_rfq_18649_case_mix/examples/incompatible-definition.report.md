# Case-mix comparison

**SYNTHETIC REHEARSAL**

Descriptive supplied-record arithmetic, not statistical significance, causation, institutional findings or a maturity ranking. Definition equality is caller-declared, not independently authenticated.

Input digest (canonical JSON, not authenticity): `6131d3db8c4b0873d62453456ca47d3e6fa702367a9bf2666014131747e598ce`

Population: Invented A/B sampled change records; not University records or a population census. Window is start-inclusive/end-exclusive.

Reference rationale: Fictional 50/50 routine/complex comparison scenario, chosen explicitly rather than estimated from either group.

| Group | Recorded eligible | Unknown outcomes | Raw supplied-row rate | Common-mix rate | Reference coverage |
|---|---:|---:|---|---|---|
| A — Fictional routine-heavy team | 110 | 0 | 82.727% (91/110) | 50.000% (1/2) | 1 |
| B — Fictional complex-heavy team | 120 | 0 | 57.500% (23/40) | 72.500% (29/40) | 1 |

## A — retained measurement definition

- **direction:** higher_is_better
- **eligible_definition:** Sampled changes initiated in the window; unknown follow-up remains in the denominator
- **event_definition:** Sampled change completed without rollback within seven calendar days
- **measure_class:** observed_outcome
- **strata_definition:** routine: one-system standard change; complex: multi-system coordinated change
- **unit:** sampled change
- **window_end:** 2026-04-01
- **window_start:** 2026-01-01

| Category | Reference weight | Events / non-events / unknown | Rate or bounds | State | Sources |
|---|---|---|---|---|---|
| complex | 1/2 | 1 / 9 / 0 | 10.000% (1/10) | COMPLETE_COUNTS | synthetic:A/complex |
| routine | 1/2 | 90 / 10 / 0 | 90.000% (9/10) | COMPLETE_COUNTS | synthetic:A/routine |

## B — retained measurement definition

- **direction:** higher_is_better
- **eligible_definition:** Sampled changes initiated in the window; unknown follow-up remains in the denominator
- **event_definition:** Sampled change completed without rollback within one calendar day
- **measure_class:** observed_outcome
- **strata_definition:** routine: one-system standard change; complex: multi-system coordinated change
- **unit:** sampled change
- **window_end:** 2026-04-01
- **window_start:** 2026-01-01

| Category | Reference weight | Events / non-events / unknown | Rate or bounds | State | Sources |
|---|---|---|---|---|---|
| complex | 1/2 | 50 / 50 / 0 | 50.000% (1/2) | COMPLETE_COUNTS | synthetic:B/complex |
| routine | 1/2 | 19 / 1 / 0 | 95.000% (19/20) | COMPLETE_COUNTS | synthetic:B/routine |

## Pairwise descriptions — higher does not necessarily mean better

### A versus B
Eligibility: NOT_COMPARABLE. DEFINITION_MISMATCH:event_definition

## Interpretation

Bounds vary only the supplied unknown outcomes and absent-category rates from 0 to 1. They are not confidence intervals; selection bias, outcome misclassification, dependence and sampling uncertainty remain unmeasured.

A common reference mix is an explicit comparison scenario, not a claim about either group's actual workload or a population estimate. No missing category is dropped or renormalized. Original definitions, counts and source locators remain in the JSON report.

