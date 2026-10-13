# AIS assessment readout - example deck (SYNTHETIC)

**Deck-to-report agreement: PASSED** (deck `AIS-READOUT-EXAMPLE-2026` checked against report `AIS-ASSESS-EXAMPLE-2026`)

> FICTION. Built only to exercise the deck-agreement engine against the example report. Not a University of Iowa readout and not a real assessment result.

Session: 45 minutes. Audience: AIS leadership, with the service owners in the room.

## Executive path

| Slide | Section | Min | Title | Drill-down |
|---|---|---|---|---|
| S-01 | purpose | 3 | Why we are in this room | - |
| S-02 | evidence | 4 | What this rests on | S-A1 |
| S-03 | strengths | 6 | What is already working | S-A6 |
| S-04 | priority_findings | 10 | The two gaps worth your time | S-A2, S-A3, S-A7 |
| S-05 | roadmap | 8 | Sequence, not a transformation | S-A4 |
| S-06 | resources | 6 | What it costs, and what we cannot cost yet | S-A5 |
| S-07 | decisions | 8 | What we need from you today | - |

## S-01 - Why we are in this room

*PURPOSE | core | 3 min*

- We assessed three service groups against four areas, using records you supplied.
- This session gives you four decisions, not a document to read later.
- Anything we could not evidence is shown as UNKNOWN rather than estimated.

**Speaker notes**

> Open by naming the three decisions on the last slide so the room knows where this lands.
> Say plainly that UNKNOWN means we did not have the record, not that the practice is absent.

## S-02 - What this rests on

*EVIDENCE BASE | core | 4 min*

- Seven supplied sources, each cited by exact version and locator.
- Two sampled record exports, twelve records each, drawn from the assessed window.
- Where one cycle of a record was supplied, we say so instead of generalising from it.

**Claims against the report**

| Mark | Cites | Measure | Deck says | Report says | Agreement |
|---|---|---|---|---|---|
| [->] | EV-004 | - | - | - | LINK-ONLY |
| [->] | EV-007 | - | - | - | LINK-ONLY |

**Speaker notes**

> If anyone challenges a number, go straight to S-A1 and read the locator aloud.
> Prompt: is there a second access-review cycle we did not receive?

## S-03 - What is already working

*VALIDATED STRENGTHS | core | 6 min*

- ESS change management: every sampled change carried a recorded test result.
- That is the practice the two priority gaps should be measured against.
- One further candidate strength is not corroborated yet and is held back.

**Claims against the report**

| Mark | Cites | Measure | Deck says | Report says | Agreement |
|---|---|---|---|---|---|
| [ok] | F-001 | changes_with_recorded_test_result | 12 | 12 | MATCH |

**Speaker notes**

> Name the ESS practice as the internal model - it is cheaper to copy a local practice than to import one.
> If asked about IAM access review: one cycle was supplied, so it is a candidate, not a validated strength.

## S-04 - The two gaps worth your time

*PRIORITY FINDINGS | core | 10 min*

- IAM deployments: the procedure requires two approvals; most sampled records show one.
- RIS recovery: backups complete, but no restoration was exercised in the window.
- Neither is a finding about individuals; both are about the record the process leaves.

**Claims against the report**

| Mark | Cites | Measure | Deck says | Report says | Agreement |
|---|---|---|---|---|---|
| [ok] | F-002 | single_approval_rate_pct | 58 | 58 | MATCH |
| [ok] | F-003 | backup_completion_rate_pct | 99 | 99 | MATCH |
| [??] | F-003 | demonstrated_recovery_time_hours | UNKNOWN (not assessed) | UNKNOWN (not assessed) | UNKNOWN-IN-REPORT |
| [ok] | F-004 | services_without_recorded_alert_owner | 2 | 2 | MATCH |

**Speaker notes**

> Lead with the approval gap: it is the one with a cheap, checkable fix.
> Do not let 99 percent backup completion stand in for recovery - say the difference out loud.
> Prompt: were the five two-approval deployments different in kind, or just better recorded?

## S-05 - Sequence, not a transformation

*PHASED ROADMAP | core | 8 min*

- 0-90: enforce the approval record (R-001) and complete the alert routing table (R-003).
- 90-180: one documented restoration exercise per critical dataset (R-002).
- 180+: extend both practices to the remaining groups (R-004) once the first phases report.

**Claims against the report**

| Mark | Cites | Measure | Deck says | Report says | Agreement |
|---|---|---|---|---|---|
| [ok] | R-001 | - | 0-90 | 0-90 | MATCH |
| [ok] | R-003 | - | 0-90 | 0-90 | MATCH |
| [ok] | R-002 | - | 90-180 | 90-180 | MATCH |
| [ok] | R-004 | - | 180+ | 180+ | MATCH |

**Speaker notes**

> Say what each phase produces as evidence; do not promise a maturity level.
> R-004 deliberately waits on the first two phases reporting - that is the dependency, not padding.

## S-06 - What it costs, and what we cannot cost yet

*RESOURCE IMPLICATIONS | core | 6 min*

- R-001: 80 staff-hours one-time, 4 staff-hours per month recurring.
- R-003: 16 staff-hours one-time; review cadence not agreed, so recurring is UNKNOWN.
- R-002 cannot be costed until dataset sizes and the restore target are supplied.

**Claims against the report**

| Mark | Cites | Measure | Deck says | Report says | Agreement |
|---|---|---|---|---|---|
| [ok] | RES-001 | one_time_effort | 80 | 80 | MATCH |
| [ok] | RES-001 | recurring_effort | 4 | 4 | MATCH |
| [ok] | RES-003 | one_time_effort | 16 | 16 | MATCH |
| [??] | RES-002 | one_time_effort | UNKNOWN (not assessed) | UNKNOWN (not assessed) | UNKNOWN-IN-REPORT |

**Speaker notes**

> Give the two real numbers first, then the UNKNOWN, so the gap reads as scope and not as evasion.
> Prompt: who can supply dataset sizes and the restore target, and by when?

## S-07 - What we need from you today

*DECISIONS REQUESTED | core | 8 min*

- D-001: enforce the two-approval rule in the IAM pipeline (0-90).
- D-002: fund a restoration exercise for critical RIS datasets (90-180).
- D-003: assign alert routing owners for the two unrecorded ESS services (0-90).

**Claims against the report**

| Mark | Cites | Measure | Deck says | Report says | Agreement |
|---|---|---|---|---|---|
| [->] | D-001 | - | - | - | LINK-ONLY |
| [->] | D-002 | - | - | - | LINK-ONLY |
| [->] | D-003 | - | - | - | LINK-ONLY |

**Speaker notes**

> Take the decisions in order and record the chosen option and its owner on the spot.
> A defer is a legitimate outcome - record what evidence would change it.

## S-A1 - Appendix - evidence register

*APPENDIX | appendix | 0 min*

- EV-004 iam-deploy-export-2026H1.csv rows 2-13, version 2026-07-01.
- EV-007 iam-access-review-2026Q1.pdf p.1-2, version 2026-04-03, single cycle.
- Each figure in the main body resolves to one of these locators.

**Claims against the report**

| Mark | Cites | Measure | Deck says | Report says | Agreement |
|---|---|---|---|---|---|
| [->] | EV-004 | - | - | - | LINK-ONLY |
| [->] | EV-007 | - | - | - | LINK-ONLY |

**Speaker notes**

> Read the locator, not the conclusion, when a number is challenged.

## S-A2 - Appendix - IAM approval sampling detail

*APPENDIX | appendix | 0 min*

- Twelve sampled deployments; seven record one approval, five record two.
- The procedure text requiring two approvals is IAM-DEP-PROC v2 section 5.1.
- The sample is a sample - whether it is representative is an open input.

**Claims against the report**

| Mark | Cites | Measure | Deck says | Report says | Agreement |
|---|---|---|---|---|---|
| [ok] | F-002 | deployments_with_single_approval | 7 | 7 | MATCH |
| [ok] | F-002 | single_approval_rate_pct | 58 | 58 | MATCH |

**Speaker notes**

> If challenged on representativeness, agree it is open and name the wider window as the test.

## S-A3 - Appendix - RIS backup versus restoration

*APPENDIX | appendix | 0 min*

- Backup completion is read from the job log; restoration is a separate record that does not exist here.
- No restoration exercise appears in the assessed window, so recovery time stays UNKNOWN.
- This is an absent record, not an observed failure to recover.

**Claims against the report**

| Mark | Cites | Measure | Deck says | Report says | Agreement |
|---|---|---|---|---|---|
| [ok] | F-003 | backup_completion_rate_pct | 99 | 99 | MATCH |
| [??] | F-003 | demonstrated_recovery_time_hours | UNKNOWN (not assessed) | UNKNOWN (not assessed) | UNKNOWN-IN-REPORT |

**Speaker notes**

> Make the distinction explicit: a completed backup is an input to recovery, not evidence of it.

## S-A4 - Appendix - phase dependencies

*APPENDIX | appendix | 0 min*

- R-004 depends on R-001 and R-002 having reported, which is why it sits at 180+.
- R-001 and R-003 touch different systems and different owners, so they run in parallel in 0-90.
- Each phase is described by the evidence it produces, not by a maturity level.

**Claims against the report**

| Mark | Cites | Measure | Deck says | Report says | Agreement |
|---|---|---|---|---|---|
| [ok] | R-004 | - | 180+ | 180+ | MATCH |
| [ok] | R-001 | - | 0-90 | 0-90 | MATCH |

**Speaker notes**

> If leadership wants R-004 pulled forward, name what evidence would be missing.

## S-A5 - Appendix - resource assumptions and open inputs

*APPENDIX | appendix | 0 min*

- R-001 80 staff-hours covers the pipeline change and the backfill of approver records.
- R-002 cannot be estimated without dataset sizes and the restore target.
- Every UNKNOWN here is an input we asked for and did not receive.

**Claims against the report**

| Mark | Cites | Measure | Deck says | Report says | Agreement |
|---|---|---|---|---|---|
| [ok] | RES-001 | one_time_effort | 80 | 80 | MATCH |
| [??] | RES-002 | recurring_effort | UNKNOWN (not assessed) | UNKNOWN (not assessed) | UNKNOWN-IN-REPORT |
| [ok] | RES-003 | one_time_effort | 16 | 16 | MATCH |

**Speaker notes**

> Offer to convert any UNKNOWN into an estimate as soon as the named input arrives.

## S-A6 - Appendix - ESS change sampling detail

*APPENDIX | appendix | 0 min*

- Twelve sampled ESS changes; twelve carry a recorded test result.
- Procedure text is ESS-CM-PROC v4 section 3.2; records are ess-change-export-2026H1.csv.
- This is the practice R-001 asks IAM to match for approvals.

**Claims against the report**

| Mark | Cites | Measure | Deck says | Report says | Agreement |
|---|---|---|---|---|---|
| [ok] | F-001 | changes_with_recorded_test_result | 12 | 12 | MATCH |

**Speaker notes**

> Use this to answer 'can we actually do this here' - the answer is that one group already does.

## S-A7 - Appendix - ESS alert routing coverage

*APPENDIX | appendix | 0 min*

- Nine ESS services in the routing table; seven name a routing owner, two do not.
- The two unnamed services are the subject of decision D-003.
- An unrecorded owner is a gap in the record, not proof that nobody responds.

**Claims against the report**

| Mark | Cites | Measure | Deck says | Report says | Agreement |
|---|---|---|---|---|---|
| [ok] | F-004 | services_without_recorded_alert_owner | 2 | 2 | MATCH |

**Speaker notes**

> If someone says 'we all know who responds', ask where that is written down.

## Open inputs

These stay UNKNOWN. None of them is presented as a zero, a pass, or a maturity level.

- `F-003.demonstrated_recovery_time_hours` - no restoration exercise recorded in the assessed window; not assessed
- `F-005.review_completion_rate_pct` - a single supplied cycle cannot establish a rate; not assessed
- `RES-002.one_time_effort` - depends on dataset sizes and the restore target, neither of which was supplied; not assessed
- `RES-002.recurring_effort` - exercise cadence not agreed; not assessed
- `RES-003.recurring_effort` - review cadence not agreed; not assessed
- Whether the fictional 12-deployment IAM sample is representative of the full change window.
- Measured RIS recovery time for any critical dataset (no restoration exercise was recorded).
- The second IAM access-review cycle record needed to corroborate F-005.
- Restoration effort and cadence for RES-002, and the alert-review cadence for RES-003.

