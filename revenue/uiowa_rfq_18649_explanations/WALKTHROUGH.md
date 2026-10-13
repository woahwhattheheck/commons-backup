# UIOWA-118 — Eight worked interpretation cases

Every value below is a **fictional teaching assumption**. These are hand-worked
expectations checked with Python arithmetic, not outputs from a specialist engine run
by this seat. The linked source versions define the relevant meaning.

## W01 — A clean receipt is not current authority

Assume all twelve cells have internally consistent source rows. The public CLI still
emits `UNTRUSTED_INSPECTION`, maps otherwise-ready cells to
`UNTRUSTED_EVIDENCE_CONSISTENT`, withholds maturity/confidence and leaves the aggregate
`HOLD_TRUSTED_AUTHORITY_REQUIRED`. Successful `verify` reports
`UNTRUSTED_INTEGRITY_ONLY`, not independently authenticated evidence.

**Read aloud:** The bytes agree with this record. We have not established independent
source authority merely by checking the receipt. **Ask:** where did the trusted host
obtain and retain the expected authority root independently of the supplied payload?

Sources: [S01](README.md#s01), [S02](README.md#s02), [S08](README.md#s08).

## W02 — Confidence and maturity answer different questions

Assume two fresh, independently rooted rows in one trusted-host cell agree on maturity
2 and declare confidence 8000 and 6500 basis points. The source-defined ready-cell rule
retains maturity 2 and uses the minimum confidence, 6500 basis points. Display conversion
is `6500 / 100 = 65` percent, or `6500 / 10000 = 0.65` as a fraction. This is declared
confidence, not a calibrated probability or 65 percent maturity.

Change the second source maturity to 3. The cell becomes `HOLD_CONFLICT` and both output
values become null. Do not average to 2.5, vote away the conflict or preserve the old
65 percent display. The schema's 0–4 range alone supplies no named rubric.

**Ask:** do the sources assess the same practice, scope and period, and what evidence
justifies their declared confidence?

Sources: [S02](README.md#s02), [S04](README.md#s04).

## W03 — Freshness has a versioned boundary

Set the teaching evaluation instant to `2026-09-19T12:00:00Z`. A source observed at
`2026-05-22T12:00:00Z` is exactly 120 days old. The pinned implementation compares
integer elapsed seconds with `120 * 24 * 60 * 60 = 10368000`: equality is not stale.
A source observed one whole second earlier exceeds the threshold and is stale.
A future source is invalid, not a fresh success. A conflict may take precedence over
the displayed stale status; the timestamps still need review.

**Read aloud:** This evidence passed this version's age check at this instant. That is
not proof it captures a material system change that happened yesterday. **Ask:** does
this practice need a more recent artifact because its relevant circumstances changed?

Sources: [S01](README.md#s01), [S02](README.md#s02), [S03](README.md#s03).

## W04 — A partial failure rate needs its denominator

Ten production deployments are eligible in one service/window. Eight have known
intervention outcomes: two true, six false. Two are unknown. The measured rate over
known outcomes is `2 / 8 = 25%`, with `eligible=10`, `used=8`, `missing=2`, coverage
`PARTIAL`. Do not publish `2 / 10 = 20%` as the complete measured rate.

A separate analyst sensitivity calculation says that if the two unknown outcomes were
both non-failures or both failures, the all-event proportion could range from 20% to
40%. That range is **not a calculator output or confidence interval**; it only shows
what these two missing classifications could change.

**Read aloud:** Two of eight classified deployments required intervention; two of ten
outcomes remain unknown. **Ask:** can their deployment records resolve the missing flags?

Source: [S05](README.md#s05).

## W05 — Matching labels can hide different clocks

For three fictional deployments, agreed change-to-production elapsed times are 2, 6 and
28 hours. Median is 6 hours; arithmetic mean is 12 hours. Both describe the supplied
sample, not labor effort. A peer using release-candidate creation instead of the earliest
constituent commit starts a different clock, so the same label does not justify a
speed ranking. Missing commit timestamps further change the used sample.

Four deployment events in an eight-day window yield 0.5 deployments/day. An event at the
exact window end is excluded, so adjacent windows do not count it twice. Frequency alone
does not establish quality or value.

**Ask:** which event starts each clock, which service is in scope, and which eligible
records were excluded from this metric?

Source: [S05](README.md#s05).

## W06 — Backup, recovery point and usable recovery are different evidence

Assume a disruption at 10:00, actual restored data from 09:30, technical restore at
10:40, required dependencies verified at 11:20 and business function verified at 11:40,
all on the same fictional UTC day with supporting exercise evidence. Observed recovery
point gap is 30 minutes. Observed RTO is 100 minutes, not the 40-minute technical restore.
Against explicitly fictional targets of 60 and 120 minutes, these observed intervals
fit both targets. This is not a University objective or observed result.

Remove business-function verification: observed RTO becomes UNKNOWN rather than 40.
Keep only a backup completion record: restoration is not demonstrated and observed
RPO/RTO are unknown. Separately, no failed deployment in a delivery window is
`NOT_OBSERVED` recovery time, not a zero-minute restore.

**Ask:** what business transaction was demonstrated, which dependencies were verified,
and what restored data point supports the recovery-point calculation?

Sources: [S06](README.md#s06), [S05](README.md#s05).

## W07 — Monthly maintenance cannot be added without a horizon

Use the resource estimator's published fictional release-case envelopes: one-time
52/84/128 person-hours and monthly maintenance 6/10/16 person-hours/month. With an
explicit three-month horizon, the combined pointwise envelope is:

| Scenario | One-time hours | Monthly hours | Three-month maintenance | Horizon hours |
|---|---:|---:|---:|---:|
| Low | 52 | 6 | 18 | 70 |
| Central | 84 | 10 | 30 | 114 |
| High | 128 | 16 | 48 | 176 |

The central point is a planning assumption, not an estimated statistical mean. Count
shared training once: twelve learners attending 1.5 hours are 18 learner person-hours,
not 36 merely because two recommendations link to the workshop. Facilitator time is a
separate activity. No hourly price, cash savings or released-capacity result follows
from these quantities.

**Ask:** what monthly recurrence, planning horizon, role allocation and shared-activity
identity supports the estimate? Does the model assume maintenance every month?

Source: [S07](README.md#s07). The values here are arithmetic replay of the source's
fictional scenario, not a fresh execution of the estimator.

## W08 — A complete-looking subtotal can hide an unscoped demand

Assume 34 known one-time person-hours and another required activity whose effort is
unassessed. The known subtotal is 34; the complete total is UNKNOWN, not 34 or zero.
If minimum specialist demand is 20 hours and maximum stated capacity is 16, the demand
exceeds even that optimistic capacity. Adding 100 hours from an unrelated role cannot
repair the skill mismatch. Conversely, a capacity envelope that fits is not a dated
schedule: dependencies and simultaneous demand may still prevent execution.

**Read aloud:** These hours are the known part of the scope; they are not a complete
quote or staffing commitment. **Ask:** which missing activity and which specialist
allocation would resolve the estimate before timing is discussed?

Source: [S07](README.md#s07).

## Presenter close

Read a result in this order: what was observed or modeled; service/group and dimension;
period and units; used versus eligible population; unknowns and conflicts; source and
version; the narrow conclusion supported; the one next evidence question. Do not let a
green-looking receipt, a low number or a tidy chart substitute for that interpretation.
