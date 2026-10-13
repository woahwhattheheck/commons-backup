# Seasonal capacity interview worksheet

UIOWA-070 preparation template. Blank entries are unresolved inputs, not negative findings. The worked packet is fictional; this template must be populated from actual engagement evidence in its approved private location. No production load test or calendar action is performed by this worksheet.

## Interview cover

| Field | Entry |
|---|---|
| Assessment group and service | UNCOLLECTED |
| Interview role and evidence owner role | UNCOLLECTED |
| Observation window, timezone and source version | UNCOLLECTED |
| Business-critical user journey and outcome | UNCOLLECTED |
| Seasonal event and calendar owner | UNCOLLECTED |
| Demand unit and denominator | UNCOLLECTED |
| Applicable service objective and operating conditions | UNCOLLECTED |
| Artifact IDs and exact locators | UNCOLLECTED |
| Known differences between documented and demonstrated practice | UNCOLLECTED |

## Ask for one concrete event, not a general assurance

| Topic | Focused interview task | Evidence to request | What the answer changes |
|---|---|---|---|
| ESS registration | Walk through one prior opening or deadline. Which user actions generated the busiest service calls? | Dated demand trace or aggregate, event calendar, workload definition, failed/slow transaction context | Incremental demand range, peak duration and relevant user journey |
| RIS research deadline | Follow a submission through identity, database, external reporting and acknowledgement. What must complete before the deadline? | Dependency map, cutoff definition/timezone, observed request profile, acknowledgement records | Dependency edges, overlap assumptions and external-service questions |
| IAM sign-in | Explain simultaneous student, staff and service demand. Which consumers share the same backend? | Aggregate service request breakdown, effective call ratios, cached/uncached behavior | Shared-resource load without counting one service as three independent resources |
| Baseline versus peak | Show whether the supplied estimate is an incremental burst, total rate, concurrency or request count. | Unit/denominator and source observation interval | Prevents adding a total on top of baseline or comparing incompatible units |
| Capacity comparability | Show the same-workload evidence for an envelope under normal and degraded operation. | Environment, data size, operation mix, concurrency, objective and measurement method | Whether a numeric envelope is usable or must remain unknown |
| Retry and batching | Trace one request through retries, batching, caching and fan-out. What is already included in the ratio? | Representative request/call profile, versioned design, observed exception paths | Effective edge ratios; avoids hidden double-counting or unwarranted deduplication |
| Maintenance | Follow one planned maintenance window through dependent service owners and user-impact checks. | Exact start/end/zone, retained-capacity evidence, owner role, communication/recovery records | Calendar conflicts, retained-capacity assumptions and viable alternatives |
| External service | Identify what is known about limits, scheduled changes and escalation, and what is only assumed. | Current dated provider/service evidence with scope and locator | Unknown versus supportable external capacity and practical follow-up |
| Staff constraints | Identify preparation work, specialist skills, support obligations and concurrent commitments by role. | Existing work estimates and confirmed role-capacity assumptions | Feasible effort and sequencing; no personal availability inferred |
| Changed assumptions | Explain which new evidence would most change the preferred option. | Explicit low/typical/high rationale and unresolved questions | Sensitivity interpretation rather than a spurious single-score recommendation |
| User outcome | Describe what demonstrates that a preparation change helped without breaking correctness or freshness. | Baseline and comparable follow-up user-journey evidence | Distinguishes calculated load reduction from demonstrated benefit |
| Recurring burden | Who maintains the improvement and how is its overhead recognized? | Ownership and estimated maintenance/support effort | One-time versus continuing resource needs |

## Editable dependency calendar

Use one row per observed or proposed window; distinguish actual and hypothetical dates. An end timestamp does not belong to the preceding window. Resolve ambiguous local time before import rather than guessing an offset.

| ID | Actual / hypothetical | Service or consumer | Start with offset | End with offset | Increment or retained-capacity range | Owner role | Evidence ID + version + locator | Unknown or disputed assumption |
|---|---|---|---|---|---|---|---|---|
| EVENT-01 | UNCOLLECTED | UNCOLLECTED | UNCOLLECTED | UNCOLLECTED | UNCOLLECTED | UNCOLLECTED | UNCOLLECTED | UNCOLLECTED |
| MAINT-01 | UNCOLLECTED | UNCOLLECTED | UNCOLLECTED | UNCOLLECTED | UNCOLLECTED | UNCOLLECTED | UNCOLLECTED | UNCOLLECTED |

## Editable dependency and capacity register

| Service ID | Group | Upstream consumers | Effective calls per request | Same-workload demand and capacity ranges | Owner role | Observation window | Exact evidence locator | Remaining question |
|---|---|---|---|---|---|---|---|---|
| SERVICE-01 | UNCOLLECTED | UNCOLLECTED | UNCOLLECTED | UNCOLLECTED | UNCOLLECTED | UNCOLLECTED | UNCOLLECTED | UNCOLLECTED |

A shared identity or database service has one resource row and separate consumer contributions. Evidence reused across consumers retains its identity; it does not become multiple independent observations. Missing limits stay unknown, even when a written plan exists.

## Compare proportionate preparation choices

| Option | Specific assumption changed | Expected modeled effect | One-time person-hours | Recurring role-hours | Skills / ownership | Dependencies | Validation needed | Unfavorable or unresolved effect |
|---|---|---|---|---|---|---|---|---|
| Calendar coordination | UNCOLLECTED | UNCOLLECTED | UNCOLLECTED | UNCOLLECTED | UNCOLLECTED | UNCOLLECTED | UNCOLLECTED | UNCOLLECTED |
| Remove redundant reference-data work | UNCOLLECTED | UNCOLLECTED | UNCOLLECTED | UNCOLLECTED | UNCOLLECTED | UNCOLLECTED | UNCOLLECTED | UNCOLLECTED |
| Improve dependency evidence | UNCOLLECTED | Reduces a named uncertainty; not necessarily demand | UNCOLLECTED | UNCOLLECTED | UNCOLLECTED | UNCOLLECTED | UNCOLLECTED | UNCOLLECTED |

Do not automatically translate person-hours into elapsed days or money. Do not count reduced generation/processing time as released staff capacity without evidence. The provided planner compares service demand scenarios; staff-capacity scheduling and economic analysis are separate interfaces.

## Worked discussion card

Open the fictional example's 10:00–10:30 UTC interval. ESS, RIS and IAM each fit their assumed application envelope, yet AUTH and DB exceed theirs. Ask: which consumers contribute most; which ratio or capacity assumption is least supported; and which feasible preparation changes the user outcome rather than merely moving the pressure?

Then compare `move-auth-maintenance` with `reduce-repeated-reads`. One adds a pressure window while lowering typical excess load; the other reduces database amplification without resolving shared identity pressure. Explain both the favorable and unfavorable results. Finally, open 12:30–13:00: the unknown cutoff and unknown EXT envelope require evidence, not a numerical guess.

## Carry into the roadmap without changing meaning

Retain the component namespace, canonical input digest, service/group, interval, native pressure/unknown state, exact source references, hypothetical change, effort range, role owner and validation question. Link any proposed recommendation to these records. Label improvements as hypotheses until a comparable follow-up demonstrates their outcome. Do not cast pressure, unknown, missing capacity or a scenario calculation into a maturity rating, audit verdict, approval or institutional finding.
