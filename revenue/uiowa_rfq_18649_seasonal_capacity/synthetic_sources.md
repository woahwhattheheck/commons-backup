# Synthetic source packet — UIOWA-070

**Every statement in this packet is invented for a software rehearsal.** No University records, actual academic-calendar dates, observed service measurements, staff schedules, external-provider commitments or engagement findings are present. Version: fictional packet 1.0, prepared September 19, 2026. Exact numeric inputs live in `synthetic.json`; the canonical JSON digest binds each generated report to those inputs.

## S01

Fictional academic-cycle calendar, April 15, 2030, UTC. The modeling horizon is 08:00–14:00, with end instants excluded. Registration adds 70/100/130 requests per second to ESS from 09:00 to 11:00. Research submission adds 20/35/50 to RIS from 10:00 to 12:00. A term sign-in surge adds 40/70/100 to IAM from 08:30 to 10:30. These are incremental sustained rates above baseline, not concurrency counts or totals. Low, typical and high are planning assumptions, not sampled percentiles.

The interviewer would request actual calendar owner, event scope, timezone, historical observation window, traffic definition, denominator, burst duration and reason to expect overlap. A date alone does not establish event demand. Differences between total and incremental traffic must be resolved before import.

## S02

Fictional same-workload service envelopes, before a 20% planning reserve:

| Service | Baseline requests/s, low / typical / high | Capacity requests/s, low / typical / high |
|---|---|---|
| ESS registration | 5 / 8 / 12 | 180 / 220 / 260 |
| RIS research submission | 2 / 4 / 6 | 80 / 100 / 120 |
| IAM sign-in frontend | 10 / 15 / 20 | 160 / 200 / 240 |
| AUTH shared identity | 3 / 5 / 7 | 100 / 120 / 140 |
| DB shared database | 5 / 10 / 15 | 160 / 200 / 240 |
| EXT external dependency | 0 / 0 / 0 direct baseline | Unknown |

These figures are invented. In real discovery, ask for evidence linking the capacity envelope to the same workload, data shape, operation mix, environment, concurrency, service objective and degraded-mode assumptions as the demand estimate. A CPU limit, infrastructure health check or vendor specification alone is not the modeled requests-per-second envelope. The reserve fraction is an explicit assumption to discuss, not a fleet policy or recommended universal threshold.

## S03

Fictional effective request-call graph. ESS calls AUTH at 0.5/0.75/1 per offered ESS request and DB twice. RIS calls AUTH once, DB three times and EXT once. IAM calls AUTH once. AUTH calls EXT at 0.05/0.1/0.2 per offered AUTH request. Every edge represents an actual effective downstream call path under the hypothetical workload, inclusive of whatever retry behavior its basis describes.

Shared dependencies are evaluated once as resources while their upstream demand contributions remain separately traceable. Independent request paths add; the same incoming root may legitimately contribute along more than one path. Conversely, one shared source of evidence does not become multiple independent observations. Ask for request profiles and retry/cache/batching behavior to decide which effective ratios are justified. No live trace is collected here.

## S04

Fictional maintenance calendar. AUTH maintenance runs 10:00–11:00 and retains one-half of its normally usable capacity. DB maintenance runs 12:00–13:00 and retains three-quarters. These fractions are assumptions, not restoration or fault-tolerance evidence.

The analyst should identify the maintained component, affected consumers, applicable capacity behavior, maintenance owner role, decision authority, support coverage, alternate windows, communication obligations, recovery evidence and any external-provider dependencies. Two maintenance records on the same service do not establish independent multiplicative effects; the planner leaves their combined capacity unknown until explicitly reconciled.

## S05

Deliberately missing fictional evidence. No external-provider capacity envelope is supplied for EXT. The fixture also names an unconfirmed research cutoff from 12:30–13:00 but supplies no RIS request-rate estimate. This is a known evidence gap, not evidence of zero demand or zero capacity.

Ask the relevant owners for service definitions, recorded limits or current support terms and a representative workload estimate. Preserve exact source version, scope and uncertainty. If evidence remains unavailable, keep it unknown, describe the operational question that cannot yet be answered and compare only those portions of the model that are actually specified.

## S06

Three hypothetical preparation alternatives, evaluated independently against the baseline:

| Alternative | Assumed person-hours, low / typical / high | Changed assumption | Evidence and practical dependency |
|---|---|---|---|
| Move AUTH maintenance | 2 / 4 / 6 | Maintenance shifts to 13:00–14:00 | Calendar owners, support coverage and retained-capacity behavior must be confirmed; the new window is not automatically safe |
| Consolidate repeated reference-data reads | 8 / 16 / 24 | ESS-to-DB ratio becomes 0.8 / 1 / 1.2 | Representative request profile; unchanged correctness, freshness and security checks; actual implementation and maintenance ownership |
| Combined preparation | 10 / 20 / 30 | Both changes above | Both evidence sets, coordination and actual available role capacity; costs are not automatically additive in a real project |

There is no purchase recommendation. The reference-data alternative does not propose removing authentication, authorization, correctness, freshness or verification checks. All changes here are hypothetical input modifications; nothing is deployed or scheduled. Person-hours estimate work, not staff availability, elapsed duration, cash cost or promised savings. Recurring support burden remains an explicit interview question.

The worked results intentionally preserve mixed outcomes: fewer typical excess service calls can coexist with more clock time exposed to possible pressure. Missing external capacity and unconfirmed demand are not fixed by either modeled alternative. The analyst must explain that distinction instead of presenting a uniformly positive transformation story.
