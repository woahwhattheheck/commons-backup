# Technical-debt investment scenarios

Evidence class: **SYNTHETIC**. Analyst scenarios only; no University findings, investment approval or confirmed staff availability.

Capacity: 50 hours at upper effort bounds. Horizon: 12 weeks.
Required scenario items: none.
Decision status: **SCENARIOS_AVAILABLE**.

## Competing portfolios

| Scenario | Selected IDs | Upper effort hours | Net saved hours, low..high |
|---|---|---:|---:|
| conservative | BASE, RETRY, SYNC | 32 | 42.00..120.00 |
| optimistic | AUTOMATE, BASE, RETRY | 40 | 4.00..140.00 |

Shared prerequisites are paid once. Overlapping benefit pools and alternatives cannot be combined. Endpoint scenarios are not statistical confidence intervals. Qualitative criticality is NOT optimized or treated as a maturity score.

## Register and deferral rationale

| ID | Service impact | Service consequence | Standalone net hours | Disposition |
|---|---|---|---:|---|
| AUTOMATE | MODERATE | Potential support savings are uncertain; no guaranteed improvement is assumed. | -20.00..68.00 | UNCERTAINTY_SENSITIVE |
| BASE | MODERATE | Enables both remediation changes; no independently counted support savings. | -10.00..-8.00 | SELECTED_IN_CONSERVATIVE_SCENARIO |
| OBSOLETE | CRITICAL | Potential service-continuity risk is not measured by current support-hour savings. | -25.00..-5.00 | NO_POSITIVE_MODELED_PAYBACK |
| POLISH | LOW | Cosmetic inconsistency with no demonstrated service interruption. | -45.00..-36.00 | NO_POSITIVE_MODELED_PAYBACK |
| REPLACE | HIGH | Alternative to RETRY against the same support workload; cannot count both savings. | 11.20..50.00 | DEFER_IN_THIS_PORTFOLIO |
| RETRY | HIGH | Repeated import retries delay fictional student-status updates. | 34.00..80.00 | SELECTED_IN_CONSERVATIVE_SCENARIO |
| SYNC | MODERATE | Fictional grant-status reconciliation occupies staff time and slows handoffs. | 18.00..48.00 | SELECTED_IN_CONSERVATIVE_SCENARIO |
| UNKNOWN | HIGH | Coupling is suspected but implementation effort and achievable savings are missing. | UNKNOWN | NEEDS_ESTIMATE |

Standalone net figures exclude prerequisite costs; the portfolio totals include them. A positive standalone value is not enough to select an item.

## Prioritized investigation questions

- **P1 UNKNOWN**: Obtain missing effort, weekly burden or reduction bounds for this dependency closure. Revisit: Obtain a bounded investigation estimate and trace the actual reporting dependencies.
- **P2 OBSOLETE**: Review service consequence before deferral; avoided risk is not valued by support-hour payback. Revisit: Validate lifecycle facts and risk treatment with the service owner; consider an explicit required-item scenario.
- **P2 REPLACE**: Review service consequence before deferral; avoided risk is not valued by support-hour payback. Revisit: Reconsider only when measured residual retries or a longer planning horizon change the comparison.
- **P3 AUTOMATE**: Validate the benefit and effort bounds that change the selected portfolio. Revisit: Run a representative offline request sample before treating the optimistic case as plausible.
- **P4 BASE**: Corroborate assumptions with a representative backlog/support sample and its observation period. Revisit: Confirm contract ownership and both dependent estimates before selecting either remediation.
- **P4 POLISH**: Corroborate assumptions with a representative backlog/support sample and its observation period. Revisit: Defer unless support burden rises, related work makes the change cheaper, or service requirements change.
- **P4 RETRY**: Corroborate assumptions with a representative backlog/support sample and its observation period. Revisit: Revisit after four representative weeks of retry logs, including a peak-cycle week.
- **P4 SYNC**: Corroborate assumptions with a representative backlog/support sample and its observation period. Revisit: Validate workload separation from import retries and measure residual reconciliation effort.

## Interpretation and provenance

All benefits assume the declared delay already includes implementation, prerequisites and adoption. This is an effort-capacity model, not a calendar/resource schedule. It omits risk reduction, regulatory obligations, procurement costs and customer value; inspect those separately before deferring high-impact work. References and OBSERVED labels are supplied evidence claims, not source authentication. Synthetic references are fictional.

Normalized register SHA-256: `f8166532338e31ee1c701061ab28939cdffbbb2c33631ffe65725c87c731636d`.
Analysis SHA-256 (canonical JSON excluding this digest): `f02493eef771373f2142d9da4c47ef9c2e659fcd0a1c40bee10abec5d8697808`.
