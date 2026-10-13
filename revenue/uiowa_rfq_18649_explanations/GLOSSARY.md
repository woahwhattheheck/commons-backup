# UIOWA-118 — Glossary

Version-bound explanatory copy; all examples are fictional. [Sources and reuse](README.md).

## ess

### ESS

**Short:** Enterprise Student Systems: one of the three assessment groups.

**Expanded:** ESS is a scope label, not a maturity level or a service-performance measure. Preserve the group together with the application, assessment dimension and evidence boundary. The pinned workshare source expands ESS as Enterprise Student Systems, not Enterprise Support Services.

**Example:** A fictional registration release may involve ESS and an IAM dependency; the shared event is not two independent confirmations.

**Source:** [S01](README.md#s01), [S03](README.md#s03).

## ris

### RIS

**Short:** Research Information Systems: an assessment group, not a single application.

**Expanded:** State which research-facing workflow and service the evidence concerns before generalizing to RIS. A group label does not establish that all services have equivalent workload, availability needs or research obligations.

**Example:** A fictional submission service observation does not establish every RIS application has the same recovery behavior.

**Source:** [S01](README.md#s01), [S05](README.md#s05).

## iam

### IAM

**Short:** Identity and Access Management: identity and access scope in the assessment.

**Expanded:** Keep evidence of identity-service behavior separate from evidence that a dependent business workflow works. The acronym identifies scope; it is not a security certification or proof of a completed access review.

**Example:** A fictional sign-in service can start successfully while a registration workflow still cannot complete.

**Source:** [S01](README.md#s01), [S06](README.md#s06).

## assessment-cell

### Assessment cell

**Short:** One group and one assessment dimension, with its own evidence and status.

**Expanded:** The pinned v2 compiler forms 3 groups by 4 dimensions: software, security, deployment and ai_readiness. Use these exact wire names at this boundary; software_development or deployment_ops are not silent aliases. Twelve cells describe the matrix shape, not twelve assessed services or twelve independent findings.

**Example:** ESS/software and ESS/security are different cells even when one release record informs both.

**Source:** [S02](README.md#s02), [S03](README.md#s03), [S04](README.md#s04).

## maturity

### Maturity

**Short:** A source-supplied practice assessment; not a value invented by this help layer.

**Expanded:** The v2 authority schema accepts integer maturity 0 through 4. That numeric range does not by itself define a named rubric, certify a practice or justify averaging across cells. Only agreeing, current, rooted evidence can carry a current cell value through the trusted-host path. Held and public-inspection cells withhold it.

**Example:** Two rooted source values 2 and 3 produce HOLD_CONFLICT, not a compromise value of 2.5.

**Source:** [S01](README.md#s01), [S02](README.md#s02), [S04](README.md#s04).

## confidence

### Confidence

**Short:** Declared evidential confidence, separate from maturity and business importance.

**Expanded:** The authority schema stores confidence_bp as an integer from 0 to 10000. For a ready cell the compiler takes the minimum across its source rows; it does not estimate a probability from the evidence. A percentage-shaped display is a unit conversion, not proof of calibration, coverage or institutional performance.

**Example:** Declared values 8000 and 6500 produce 6500 basis points in an otherwise-ready trusted cell; 65 percent is not a measured chance that the institution is mature.

**Source:** [S02](README.md#s02), [S04](README.md#s04).

## basis-points

### Basis points

**Short:** 100 basis points equal one percentage point.

**Expanded:** Display confidence_bp divided by 100 as percentage points, while retaining its declared-confidence label. Do not divide by 10000 and then label that decimal as a percent. The conversion changes the unit, not the evidential authority.

**Example:** 6500 basis points = 65 percent; 0.65 is the corresponding fraction.

**Source:** [S04](README.md#s04).

## evidence-authority

### Evidence authority

**Short:** Independently retained source authority, not merely a matching checksum.

**Expanded:** The candidate names requested source IDs; the evidence-authority bundle carries the source records; a trusted host supplies an expected root independently. Equality verifies the supplied binding. The module cannot authenticate how that root was obtained, and deriving the expected root from the same untrusted payload does not establish independent provenance.

**Example:** A file and a freshly computed matching hash prove consistency of those bytes, not who authorized the evidence.

**Source:** [S01](README.md#s01), [S04](README.md#s04).

## public-inspection

### Public inspection

**Short:** A non-authorizing view of evidence consistency.

**Expanded:** The public CLI emits UNTRUSTED_INSPECTION. Otherwise-ready cells become UNTRUSTED_EVIDENCE_CONSISTENT with null maturity and confidence, and the aggregate remains HOLD_TRUSTED_AUTHORITY_REQUIRED. Successful command execution is not current review authority, buyer acceptance or approval.

**Example:** All twelve internally consistent cells can still leave the entire public packet on HOLD.

**Source:** [S01](README.md#s01), [S02](README.md#s02), [S08](README.md#s08).

## historical-replay

### Historical replay

**Short:** A reproducible view at a stated past time, not current authority.

**Expanded:** Historical compilation emits HISTORICAL_*_NON_CURRENT states. Current verification re-evaluates evidence using verifier-owned UTC. A historical success cannot be relabeled as a current result merely because its receipt still verifies.

**Example:** An unchanged report can retain valid integrity while its evidence later becomes stale.

**Source:** [S01](README.md#s01), [S02](README.md#s02).

## missing-evidence

### Missing evidence

**Short:** No rooted source record for this cell; not proof the practice is absent.

**Expanded:** The compiler emits HOLD_MISSING_EVIDENCE with null maturity and confidence. Distinguish material not supplied, a scope never assessed, and a documented search that found no record. The first state alone does not establish the latter two.

**Example:** Say no rooted source record is available for this cell, not the team never performs the practice.

**Source:** [S01](README.md#s01), [S02](README.md#s02).

## stale-evidence

### Stale evidence

**Short:** Evidence exceeds this component's stated age limit at its evaluation time.

**Expanded:** The pinned v2 constant is 120 days. The implementation compares integer elapsed seconds with that limit; it is not a universal freshness policy for every specialist tool. Retain observed_at, evaluated_at and the rule/version. Staleness withholds a current value; it does not erase historical evidence or prove deterioration.

**Example:** At exactly 120 days evidence is not stale by this rule; at 120 days plus one whole second it is stale.

**Source:** [S01](README.md#s01), [S02](README.md#s02), [S03](README.md#s03).

## conflicting-evidence

### Conflicting evidence

**Short:** Rooted source maturity values disagree; both readings need reconciliation.

**Expanded:** The v2 compiler returns HOLD_CONFLICT with null maturity and confidence rather than averaging. This conflict check precedes its stale status check, so a conflict status is not evidence that all sources are fresh. Preserve source IDs and timestamps as well as the displayed status.

**Example:** Values 2 and 3 remain a conflict even when one row is old; investigate scope, time and provenance before resolving it.

**Source:** [S02](README.md#s02).

## source-locator

### Source locator

**Short:** The place a reader can inspect the supporting material.

**Expanded:** Retain source ID, source reference, exact content digest and version together. A locator can resolve while a claim remains unsupported, and a digest can match without establishing independent authority. A component/schema namespace prevents unrelated equal-looking IDs from being joined accidentally.

**Example:** Finding F-1 in one plan is not automatically finding F-1 in another plan.

**Source:** [S01](README.md#s01), [S04](README.md#s04), [S07](README.md#s07).

## observation-window

### Observation window

**Short:** The bounded period and service population used for a measurement.

**Expanded:** The delivery calculator uses start-inclusive, end-exclusive windows and offset-aware timestamps normalized to UTC. A comparison needs the same service context, event definition, linkage rule and window treatment; identical labels alone do not make measurements comparable.

**Example:** An event at the exact end timestamp belongs to the next window, not both windows.

**Source:** [S05](README.md#s05).

## lead-time

### Change lead time

**Short:** Elapsed time from the agreed change timestamp to production deployment.

**Expanded:** The delivery tool summarizes hours over deployments with known commit_at. Its agreed change/batch timestamp must be documented: earliest commit, merge or release candidate can describe different clocks. This is not total request-to-delivery time, developer working time or individual productivity.

**Example:** A fictional change timestamp of 09:00 and production deployment at 15:00 give 6 elapsed hours.

**Source:** [S05](README.md#s05).

## deployment-frequency

### Deployment frequency

**Short:** Production deployment count over an explicit time window.

**Expanded:** The calculator reports count, deployments per day/week and median observed interval. Use one service or the required explicit service filter. More deployments alone do not establish better quality or more valuable output.

**Example:** Four production deployments in an eight-day window are 0.5 per day, regardless of how many commits each deployment contained.

**Source:** [S05](README.md#s05).

## change-fail-rate

### Change fail rate

**Short:** Failed deployments divided by deployments with known intervention outcomes.

**Expanded:** Here failure means a production deployment requiring immediate remedial intervention. Unknown intervention_required values remain outside the known-outcome denominator and make coverage PARTIAL. Report both used and eligible counts; unrelated infrastructure incidents do not enter this deployment-failure denominator.

**Example:** Two failures among eight known outcomes from ten eligible deployments give 25 percent over known outcomes, with two unknowns.

**Source:** [S05](README.md#s05).

## deployment-rework

### Deployment rework rate

**Short:** The share of known-outcome deployments that were unplanned production rework.

**Expanded:** The delivery tool divides unplanned-rework deployments by deployments with known unplanned_rework values. Ordinary planned enhancement or maintenance is not automatically rework. Missing values remain explicit rather than being assumed false.

**Example:** One unplanned incident-fix deployment among four known rework outcomes gives 25 percent, not a measure of all engineering effort.

**Source:** [S05](README.md#s05).

## coverage

### Metric coverage

**Short:** How many eligible inputs actually contributed to this metric.

**Expanded:** Delivery metrics retain eligible, used and missing counts. COMPLETE means the eligible inputs for that metric are present; PARTIAL means some are unknown; NOT_OBSERVED means no qualifying event. These statuses are not interchangeable with assessment maturity, resource-plan completeness or service health.

**Example:** Eight known outcomes out of ten eligible deployments support a partial rate, not a complete ten-event rate.

**Source:** [S05](README.md#s05).

## failed-deployment-recovery

### Failed deployment recovery time

**Short:** Elapsed recovery time for qualifying failed production deployments.

**Expanded:** This delivery metric uses only failures requiring intervention and known recovery timestamps. It is not a general disaster-recovery RTO or a mean over every infrastructure incident. No qualifying failure is NOT_OBSERVED, not zero-minute recovery.

**Example:** No failed deployment in the selected window leaves recovery time unobserved even when deployment frequency is known.

**Source:** [S05](README.md#s05).

## backup-restoration

### Backup versus restoration

**Short:** A completed backup job does not demonstrate a usable restored service.

**Expanded:** The recovery kit separates successful backup, actual data restoration, required dependency verification and business-function verification. It can report backup EVIDENCED while restoration remains NOT_DEMONSTRATED. Missing exercise evidence is not proof the backup failed.

**Example:** A backup completion record alone leaves observed RPO and RTO unknown.

**Source:** [S06](README.md#s06).

## rpo

### Recovery point objective and observed recovery point

**Short:** RPO concerns recoverable data age, not how long restoration takes.

**Expanded:** Separate the target from the observed result. In the recovery kit observed RPO is the interval from the actual restored data point to the disruption/reference time. A backup schedule alone does not establish that data point or prove the target was achieved.

**Example:** Restored data from 09:30 at a 10:00 disruption gives an observed 30-minute recovery-point gap.

**Source:** [S06](README.md#s06).

## rto

### Recovery time objective and observed recovery time

**Short:** RTO concerns elapsed time until the required business function is usable.

**Expanded:** Separate the target from observed performance. This kit measures to evidenced business-function verification, with required dependencies verified no later than that endpoint. Technical restore completion alone leaves observed RTO UNKNOWN.

**Example:** Disruption at 10:00, technical restore at 10:40 and business verification at 11:40 give 100 minutes, not 40.

**Source:** [S06](README.md#s06).

## one-time-effort

### One-time effort

**Short:** Person-hours needed once for implementation, process change and training.

**Expanded:** The resource estimator computes units multiplied by hours per unit, separately by activity and role. Person-hours are not elapsed calendar hours. Shared activities count once by activity identity even when linked to several recommendations; duplicate semantic work still needs analyst reconciliation.

**Example:** Twelve learners attending 1.5 hours require 18 learner person-hours; facilitator effort is additional.

**Source:** [S07](README.md#s07).

## recurring-effort

### Recurring effort

**Short:** Maintenance person-hours per month, separate from one-time work.

**Expanded:** The estimator multiplies monthly maintenance by explicit planning_months before combining horizon effort. Do not pre-multiply the monthly frequency by the horizon in the input. This models labor demand, not money, savings, released capacity or an approved staffing commitment.

**Example:** 10 person-hours/month over 3 months adds 30 person-hours to an 84-hour one-time central scenario: 114 hours.

**Source:** [S07](README.md#s07).

## scenario-range

### Planning scenario range

**Short:** Conditional low, central and high assumptions; not a confidence interval.

**Expanded:** The resource estimator combines nonnegative factors pointwise. Its central point is not a statistically estimated mean, and its envelope does not model correlations, seasonality or scheduling. Label the assumptions and horizon before showing the range.

**Example:** 52/84/128 one-time hours plus 3 months of 6/10/16 monthly hours gives 70/114/176 horizon hours.

**Source:** [S07](README.md#s07).

## unknown-total

### Known subtotal versus complete total

**Short:** A known subtotal remains incomplete when an estimate or scope is missing.

**Expanded:** The estimator retains known_hours separately from nullable total_hours. Null is unassessed; zero means explicitly assessed zero. COMPLETE_INPUTS still does not mean capacity is known, scope is factually sufficient or the work fits an achievable schedule.

**Example:** 34 known hours plus an unassessed activity is not a complete 34-hour estimate.

**Source:** [S07](README.md#s07).

## specialist-capacity

### Specialist capacity

**Short:** Net available hours for the required role and period, not interchangeable staffing.

**Expanded:** Implementation capacity and maintenance capacity must be nonoverlapping allocations. Another role's spare hours do not remove a specialist bottleneck. Envelope checks are necessary workload comparisons, not a calendar or approved staffing plan.

**Example:** 20 specialist hours of minimum demand exceed a stated maximum of 16; 100 unrelated developer hours do not change that comparison.

**Source:** [S07](README.md#s07).

