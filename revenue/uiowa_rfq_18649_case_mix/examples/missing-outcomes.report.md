# Case-mix comparison

**SYNTHETIC REHEARSAL**

Descriptive supplied-record arithmetic, not statistical significance, causation, institutional findings or a maturity ranking. Definition equality is caller-declared, not independently authenticated.

Input digest (canonical JSON, not authenticity): `88d70a2e8a8622263ae7c68300f29fc45e1eaefaa9bfbd9acd517bd41a0c77fa`

Population: Invented A/B sampled change records; not University records or a population census. Window is start-inclusive/end-exclusive.

Reference rationale: Fictional 50/50 routine/complex comparison scenario, chosen explicitly rather than estimated from either group.

| Group | Recorded eligible | Unknown outcomes | Raw supplied-row rate | Common-mix rate | Reference coverage |
|---|---:|---:|---|---|---|
| A — Fictional routine-heavy team | 110 | 0 | 82.727% (91/110) | 50.000% (1/2) | 1 |
| B — Fictional complex-heavy team | 120 | 20 | 57.500% to 74.167% [23/40, 89/120] | 72.500% to 82.500% [29/40, 33/40] | 1 |

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
- **event_definition:** Sampled change completed without rollback within seven calendar days
- **measure_class:** observed_outcome
- **strata_definition:** routine: one-system standard change; complex: multi-system coordinated change
- **unit:** sampled change
- **window_end:** 2026-04-01
- **window_start:** 2026-01-01

| Category | Reference weight | Events / non-events / unknown | Rate or bounds | State | Sources |
|---|---|---|---|---|---|
| complex | 1/2 | 50 / 30 / 20 | 50.000% to 70.000% [1/2, 7/10] | UNKNOWN_OUTCOMES | synthetic:B/complex |
| routine | 1/2 | 19 / 1 / 0 | 95.000% (19/20) | COMPLETE_COUNTS | synthetic:B/routine |

## Pairwise descriptions — higher does not necessarily mean better

### A versus B
Eligibility: DECLARED_DEFINITIONS_MATCH. 
Raw supplied-row order: A_HIGHER; common-mix order: B_HIGHER.
Uniform aggregate reversal: ROBUST_WITHIN_SUPPLIED_OUTCOME_BOUNDS.
Common-mix difference (first minus second): -32.500% to -22.500% [-13/40, -9/40].

## Interpretation

Bounds vary only the supplied unknown outcomes and absent-category rates from 0 to 1. They are not confidence intervals; selection bias, outcome misclassification, dependence and sampling uncertainty remain unmeasured.

A common reference mix is an explicit comparison scenario, not a claim about either group's actual workload or a population estimate. No missing category is dropped or renormalized. Original definitions, counts and source locators remain in the JSON report.

