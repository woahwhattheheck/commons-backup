# Component maintenance: worked rehearsal and decision brief

**UIOWA-056. Every component, service, advisory, source locator and effort estimate below is fictional. This is an internal facilitator example, not a University of Iowa finding or an authorization to change a system.**

The [interview instrument](INTERVIEW.md) is usable without running software. This worked example explains how to use it: preserve the difference between a component being present, its recorded support status, advisory applicability and reported exposure. A polished register should not make a weak source claim stronger.

## What the exercise contains

The rehearsal date is September 19, 2026. Its seven component records refer to three fictional service IDs: ESS-DEMO, RIS-DEMO and IAM-DEMO. The source fixture supplies a 120-day evidence-age limit and a 90-day planning horizon. Those numbers are adjustable preparation assumptions, not a prescribed service-level agreement or a standards requirement.

The following values were reproduced from the supplied fictional input using the source in [PR #16207 at commit 59d94dfa](https://github.com/woahwhattheheck/commons/tree/59d94dfa2d1441aa05bfe89a9bd6d8256bbf6f36/revenue/uiowa_rfq_18649_components). The link identifies the internal build evidence, not a customer delivery destination. Local execution and this documentation do not establish that executable integration has passed its separate repository checks.

| Component | Service scope | Qualified support | Support evidence | Advisory interpretation |
|---|---|---|---|---|
| C01 | ESS-DEMO, IAM-DEMO | Supported | Current supplied record | No advisory record supplied; not a no-vulnerabilities assertion |
| C02 | ESS-DEMO, RIS-DEMO | Unsupported | Current supplied record | Affected; reported exposure unknown; open |
| C03 | IAM-DEMO | Unknown | Missing | Both applicability and reported exposure unknown; expired exception |
| C04 | RIS-DEMO | Ending soon | Current supplied record | Affected; reported exposure unknown; unverified closure |
| C05 | RIS-DEMO | Unknown | Stale | No advisory record supplied; historical unsupported label is not current proof |
| C06 | ESS-DEMO, IAM-DEMO | Supported | Current supplied record, no end date | Affected; reported exposure confirmed; current recorded exception |
| C07 | IAM-DEMO | Supported | Current supplied record | Not affected; exposure not observed; documented closure on supplied records |

The support counts are three supported, one ending soon, one unsupported and two unknown. There are five advisory records and five component-level maintenance items. These counts describe the supplied fixture. They do not estimate the completeness of a real component inventory or advisory feed.

## Walk C02 through the interview

C02 is one inherited component shared by ESS-DEMO and RIS-DEMO. Its supplied support end date is August 31, 2026, with a current support record. Its component owner is absent, its review date has passed, and its advisory says affected without a current exposure determination.

The first decision is not “two applications have confirmed vulnerabilities.” That sentence would invent exposure and multiply a shared component into two findings. The supported statement is narrower: the supplied component record is unsupported, two service IDs depend on it, and the advisory's exposure context remains unknown.

Ask which role owns the inherited maintenance decision, which source establishes the current support arrangement, and what evidence will determine the service context of the advisory. Then ask how compatibility review, change preparation and verification would cover both consumers. Do not request exploit reproduction or production credentials.

The proposed practice change is one coordinated maintenance decision. The fixture supplies a 5–9 person-day preparation estimate for that component. Preserve both service references on the same item; do not silently turn the estimate into 10–18 days. Equally, do not assume all consumer-specific work is free. A real estimator must say which shared and consumer-specific activities are included and revise the bounds when evidence changes.

## Five other interpretation traps

**C03: a label is not its supporting evidence.** The input contains not-affected and confirmed-exposure labels without their required supporting references. Both qualified states remain unknown. The recorded exception expired on September 18, and no owner is supplied. Ask for applicability evidence, exception authority and a responsible role. Its effort remains unestimated; unknown effort is not zero effort.

**C04: resolving a ticket is not the same as establishing closure.** Support ends on October 19, the inventory evidence is stale, no review cadence is recorded, and the advisory's resolved label lacks closure evidence. The worksheet retains unverified closure rather than presenting a completed remediation. Ask what was checked, when, against which component/advisory, and where that result is recorded.

**C05: a historical negative can also be stale.** An old unsupported statement does not establish today's support status. A replacement, a changed version or a different support arrangement might have occurred; none is assumed. Preserve the historical label, mark the current qualified state unknown and identify who can reconcile the inherited record.

**C06: an exception does not erase reported exposure.** The supplied affected and confirmed-exposure records remain visible alongside a current recorded exception. Its expiry is September 20, so it needs review within the rehearsal's planning horizon. Separately, the supported component has no recorded end date; ask how its maintenance horizon will be established. A spreadsheet entry does not itself grant or extend an exception.

**C07: documented does not mean independently authenticated.** The supplied current, scoped records support the instrument's documented-closure label. They do not prove the source is genuine, that a live system was tested, or that every advisory was collected. Not observed remains different from proof of absence. The record can be used with those limits intact.

## Maintenance queue and effort communication

| Component | Proposed preparation focus | Supplied low days | Supplied high days |
|---|---|---:|---:|
| C02 | Establish inherited owner; resolve overdue review and exposure context; plan supported maintenance path | 5 | 9 |
| C03 | Establish support/applicability evidence and advisory owner; review expired exception | UNKNOWN | UNKNOWN |
| C04 | Refresh inventory; establish review cadence; plan support transition; verify closure | 2 | 3 |
| C05 | Establish inherited owner and current support evidence | 1 | 2 |
| C06 | Establish support horizon and review exception before expiry | 1 | 2 |

The known subtotal is **9–16 person-days, plus one unestimated item**. All five rows have workflow priority 2 in this fixture: time-sensitive maintenance or review. The priority is not a vulnerability severity score, a maturity score or a delivery commitment. The subtotal is not a programme duration or fixed price; it excludes the unknown estimate and says nothing about staff availability, sequencing or parallel execution.

A faithful verbal summary is: “Our fictional records produce five maintenance questions. Four have supplied preparation bounds totalling 9–16 person-days; the fifth is still unestimated. We need evidence and owner decisions before treating this as a complete plan.”

An unfaithful summary would be: “The assessment found five vulnerabilities and the whole fix takes sixteen days.” It replaces questions with findings, drops uncertainty and mistakes effort for elapsed duration.

## Record the next decision, not a premature finding

Use the decision record in INTERVIEW.md or the engagement's existing tracker. For C02, record the exact component/version, both service IDs, the unknown inherited owner, the specific evidence request, the 5–9 day supplied bounds and their scope limits. Proposed decision: Investigate, then Plan when the necessary evidence and owner process support it. Do not mark an owner assignment, exception acceptance, calendar date or system change as completed merely because it appears in the preparation record.

Preserve the original supplied version. A corrected source record should produce a new assessment version, not an undocumented edit to a generated status. A report's checksums can show that bytes match an expected bundle, but only independent regeneration from the supplied input tests whether its outputs agree with this evaluator. Neither procedure authenticates the real-world source. The separate executable carrier includes that regeneration verifier; this document does not execute it.

Close the rehearsal by asking: “Which of these statements follows from a record, which is a planning assumption, and which is still a question?” Retain unresolved answers instead of replacing them with a convenient average or a clean-looking dashboard.

## Attribution and scope of publication

Prepared by **ZZ-KESTREL-731 / GPT-6 Astra Pro**, operation `uiowa-056-kestrel731-20260919`, work record [#16113](https://github.com/woahwhattheheck/commons/issues/16113). The standalone interview and this worked rehearsal are inert documentation. Their publication does not certify or release the executable code, publish the XLSX binary, contact a prospect, schedule a meeting, or authorize access to any institution's systems.
