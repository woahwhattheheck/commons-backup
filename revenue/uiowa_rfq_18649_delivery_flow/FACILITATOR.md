# Delivery-flow review — facilitator and worked rehearsal

**UIOWA-062. Synthetic practice instrument, not University findings.**
This document can be used without running software. The accompanying tool derives
measurements from supplied records; the assessor supplies interpretation and
corroboration. No appointments, changes, purchases or release decisions are made
by this packet.

## Frame a review that practitioners can answer

Select one recent ordinary change and one exception or urgent maintenance change
for each relevant service pattern. Record why those examples were selected, what
was unavailable and which delivery patterns remain uncovered. A handful of cases
is not a statistical estimate of team performance. Compare analogous outcomes
across stacks rather than requiring one pipeline vendor or branching model.

Capture the trace ID, service, owning organizational role, change reference,
request time, observation cutoff/timezone, release cadence and source export
coverage. Identify shared stages once; a shared service does not create three
independent examples just because ESS, RIS and IAM consume it. Record the person
or role interpreting each source without grading individual employees.

### Reusable five-stage evidence worksheet

Copy this table for every sampled change. Keep quoted accounts separate from
source observations. Write UNKNOWN where information is unavailable.

| Stage | Evidence to locate | Questions for the practitioner | Record and locate |
|---|---|---|---|
| Build | Source revision, input/dependency versions, build invocation, attempts, produced artifact identity | Can this exact source/input state be rebuilt? Which inputs are not recorded? What changed between attempts? | Source locator; attempt IDs; input/version gaps; owner role |
| Verification | Selected test/check records including failures, repeats, parallel checks and exemptions | What does each passing check establish? Was a repeated run unchanged, repaired or differently configured? Which paths are not tested? | Failure and retry relationship; scope; queue/start/finish; contradictory account |
| Packaging | Package identity, included configuration, packaging verification and retention | Is the packaged object the one that was verified? Where do manual steps or inherited dependencies enter? | Artifact/version linkage; unknown transitions; maintenance owner |
| Promotion | Decision record, expected prerequisites, manual/automated transitions and exception handling | What is the waiting period for? Is the decision window intentional? Who handles absence or emergency changes? | Decision evidence, explicit queued/running/unknown state, rationale and owner |
| Deployment | Deployment record, target/version, observed result and verification of service behavior | What shows that the intended version reached the target? What verifies the business behavior afterward? | Source locator, finish/result, unverified assertions, operational handoff |

For every source, retain an evidence ID, exact locator, recorded/observed dates,
export window and limitations. Redact secret values and unnecessary personal or
production data before sharing assessment packets. This instrument requires
metadata, not credentials, live system access or private production content.

## Worked trace A — parallel work and a manual decision

**Fictional ESS course catalog.** All times are UTC on September 1, 2026. The request
is 09:00 and the observation cutoff 10:00. The source is the supplied fictional
attempt array at `synthetic.json#/traces/0/attempts`, evidence ID E1 in that trace.

| Attempt | Stage / step | Queue | Start | Finish | Result |
|---|---|---|---|---|---|
| B1 | Build / package | 09:00 | 09:02 | 09:07 | Success |
| V1 | Verification / unit, attempt 1 | 09:07 | 09:08 | 09:12 | Failure |
| V2 | Verification / unit, attempt 2 | 09:12 | 09:13 | 09:17 | Success |
| I1 | Verification / integration | 09:07 | 09:08 | 09:18 | Success |
| P1 | Packaging / archive | 09:18 | 09:19 | 09:21 | Success |
| M1 | Promotion / manual review | 09:21 | 09:31 | 09:33 | Success |
| D1 | Deployment / release | 09:33 | 09:34 | 09:38 | Success |

**Actual derived quantities.** Per-attempt execution sums to 31 minutes; its elapsed
union is 23 minutes. Queue union is 16 minutes, including a 10-minute manual queue.
Queue and execution overlap for one minute, giving **16 + 23 − 1 = 38 minutes** of
observed activity. The remaining 22 minutes of the observation window includes the
period after deployment; calling it waste would be unsupported. Both failure-time
and repeated-attempt-time lower bounds are four minutes. They are distinct views,
not additive savings. If the repeat also failed, its duration would belong to both.

**Facilitator prompts.** Was V2 an unchanged rerun or changed work? Which retained
input/commit records establish that? Would shortening V2 affect the completion
path while I1 runs until 09:18? Was M1 waiting for an intentional release window,
missing information, unavailable decision ownership, or something else? The trace
does not answer those causal questions.

**Supportable outcome.** The supplied trace records parallel verification, a failed
then successful unit attempt and a manual promotion wait. The proposed investigation
is to classify repeated-run causes and promotion-wait reasons on a broader sample.
Do not recommend removal of the review or claim eight minutes of recoverable labor.
The supplied `observed_match` reproducibility label has a source locator but has not
been independently substantiated by artifact comparisons in this rehearsal.

## Worked trace B — incomplete observation

**Fictional RIS grant routing.** Request 09:00, cutoff 10:00. Build B1 ran 09:04–09:15.
Verification V1 began 09:16 and is explicitly running at cutoff. Packaging P1 is
explicitly queued since 09:20; promotion M1 has a queue timestamp but its current
progress is unknown. See `synthetic.json#/traces/1/attempts`.

The running interval contributes a **44-minute observed lower bound**, not a final
runtime. P1 contributes a **40-minute queue lower bound**, not a completed wait.
M1 contributes **UNKNOWN**, not 40 minutes. These intervals overlap: execution union
55 minutes, queue union 43, overlap 40, combined observed activity 58. Two minutes
of the hour have no supplied interval. There is no deployment finish to report.

**Evidence request.** Obtain a later export for V1/P1 with a new cutoff, the actual
current state for M1 and the roles maintaining packaging/promotion. Ask whether
reproducibility has been demonstrated; a written procedure is only documented
intent. Keep the original snapshot so a later completion cannot retrospectively
make the earlier report complete.

**Disposition.** Mark the duration questions pending and preserve their lower-bound
labels. A subsequent shorter apparent duration means the original state, timestamps
or clock assumptions need reconciliation; do not silently edit the old record.

## Worked trace C — successful label, missing history

**Fictional IAM affiliation sync.** Build B2 is labeled successful at 09:10, but its
start time and attempt 1 are missing. Deployment D1 ran 09:13–09:14 and is labeled
successful without an evidence reference. See `synthetic.json#/traces/2/attempts`.
Verification, packaging and promotion have no supplied records.

Only one minute of execution and one of queue time are measured. The build's queue
and execution durations remain unknown. The tool records a 14-minute first reported
deployment latency while separately flagging the unreferenced record. A completed
label does not establish release approval, trace completeness or working service
behavior. An ordinal gap does not prove that the missing first attempt failed.

**Evidence request.** Locate the original build attempt(s), the missing start,
the deployment source and any shared/combined-stage records. Ask whether omitted
stages exist elsewhere or the export is incomplete. Do not conclude the team does
not test or has no promotion controls from this packet.

## From evidence to practical improvements

Use these as conditional investigation options, not prescribed University findings.
Effort is stated as work content and dependencies, not vendor cost or committed
staff availability.

| Condition established in a wider sample | Practice option | Effort and dependency to estimate | Observable result |
|---|---|---|---|
| Repeated unchanged attempts obscure intermittent failures | Record rerun reason, input identity and triage disposition in the existing workflow | Add metadata/capture and maintain review ownership; needs stable attempt/source IDs | Unknown rerun reasons decrease; failures reach an explicit disposition |
| Manual promotion waits repeatedly lack a decision owner or prerequisites | Publish owner/backup role and a compact ready-for-review packet | Align decision roles and required evidence; preserve necessary review windows | Fewer waits with unknown reason; decisions retain traceable evidence |
| Missing starts or state snapshots prevent interpreting duration | Capture start/end/current-state and export coverage together | Instrument the existing queue/runner interfaces; align clocks and state semantics | More complete/censored measurements, fewer ambiguous durations |
| Build inputs and artifact identity cannot be reconciled | Retain source/input/artifact links within the current delivery tooling | Agree the relevant input boundary and storage/retention ownership | A sampled artifact can be traced and a repeat demonstration explained |
| Stage work is shared but each team separately reconstructs it | Reuse a shared evidence reference with explicit consuming-service context | Agree common identifiers, source ownership and applicability boundaries | One maintained record supports several contextualized assessments without double-counting |

## Review and disagreement register

| Trace / question ID | Stated account and source | Observed record and locator | Agreement, conflict or different scope/period? | Follow-up / accountable role | Disposition / report revision |
|---|---|---|---|---|---|
| ESS / FAILED_ATTEMPT V1 | UNKNOWN — ask rerun reason | V1 failure, V2 success; E1 | Cause not established | Delivery-maintenance role; retain input differences | Pending, not a defect finding |
| RIS / TIME_COVERAGE M1 | UNKNOWN | Queue timestamp, unknown progress; E1 | State missing | Promotion-maintenance role; later snapshot | Pending; queue duration UNKNOWN |
| IAM / UNREFERENCED_RECORD D1 | Supplied success label | No supporting reference | Record not corroborated | Release-maintenance role; exact source locator | Pending; not release approval |
| Add case | Account / date / role | Locator / version / export window | Preserve competing explanations | Concrete question / role / dependency | Supported, revised, withdrawn or unresolved; why |

Close the review by reading back the supported observations, unknowns and proposed
follow-ups. Let practitioners correct scope and terminology. Retain unresolved
accounts rather than choosing the most polished one. State which service patterns
were not sampled and which outcomes need additional evidence. A completed worksheet
means the review is documented, not that changes are authorized or implemented.

## Attribution and replay

COPPERLEAF-63 originated UIOWA-062 and the parallel-time/censoring design in
[the existing work record](https://github.com/woahwhattheheck/commons/issues/16100).
HALYARD-86-D62 authored this recovery, its worked cases and the 38-method suite.
The historical 43-test result remains COPPERLEAF's report, not this run.

Replay the numbers with `delivery_flow.py --input synthetic.json --format json`
from this package directory. The same exact supplied bytes produce the same report
in normal and optimized Python. The report source digest binds the fixture bytes;
it does not authenticate the fictional observations or prove real University practice.
