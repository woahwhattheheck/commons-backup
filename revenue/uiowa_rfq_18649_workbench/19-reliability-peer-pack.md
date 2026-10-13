# UIOWA-019 — Deployment and service reliability peer evidence

**Prepared:** 2026-09-19  
**Source class:** official public peer-university IT material  
**Status:** proposal/assessment preparation evidence; non-authoritative  
**Intended use:** discovery design and benchmark interpretation for University of Iowa RFQ 18649

> This pack does **not** assert findings about Iowa, assign maturity scores, certify compliance, or recommend procurement. Peer material is used to sharpen questions and evidence requests. A published target is not an achieved result; a case study is not a policy; a historical metric is not a current benchmark.

## 1. Evidence interpretation rules

For every peer example below, keep the evidence class explicit:

| Evidence class | What it can support | What it cannot support by itself |
|---|---|---|
| Policy/process description | Questions about governance, ownership, workflow, control points, and artifacts | A claim that the process is consistently followed or effective |
| Service-specific operating agreement | Concrete examples of roles, targets, maintenance, release, and continuity design | Institution-wide maturity or current enterprise practice |
| Case study/accomplishment | Evidence that a described implementation or migration occurred in the stated context | Causal attribution, universal practice, or sustained performance |
| Published target/SLA | A comparison of target definitions and operating expectations | Actual attainment unless observed results are separately reported |
| Measured outcome | A historical/current observation for the defined population and period | Cross-peer comparison without matching definitions, periods, denominators, exclusions, and service boundaries |

## 2. Peer evidence register

### Stanford University IT — change governance, ownership, and incident learning

**Change management.** Stanford University IT publishes a formal process for production changes and states that changes are recorded and authorized. Its risk/impact guidance sets minimum lead times of **10 business days for Risk 1 / Very High**, **5 business days for Risk 2 / High**, and **1 business day for Risk 3 / Moderate**; Risks 4 and 5 have no minimum lead time. Standard changes use pre-approved templates, while emergency changes may be reviewed by ECAB after service restoration. Extended maintenance is announced to CAB **4–6 weeks** in advance.

**Service ownership.** Stanford's service-management toolkit assigns the Service Owner accountability for service success/value and includes strategy, information integrity, budget, security/compliance/resiliency, vendor performance, high-risk change approval, and major-incident escalation responsibilities. Its current toolkit also expects catalog information to include availability, maintenance windows, criticality, response times, ownership, and change/notice information.

**Problem management.** Stanford describes a flow in which a Problem record may be created after a Major Incident or from incident patterns; subject-matter experts perform RCA, and Problem Management closes the problem only after the RCA is considered sufficient.

**Transferable use:** ask Iowa how change risk, lead time, emergency handling, service ownership, major-incident escalation, RCA, and corrective action closure are actually evidenced for ESS, RIS, and IAM.

**Do not infer:** Stanford's published workflow does not prove Iowa should copy its CAB model, nor does it provide an empirical change-success benchmark.

Sources:
- https://uit.stanford.edu/service/changemgt
- https://uit.stanford.edu/service/changemgt/leadtimes
- https://uit.stanford.edu/service-management/toolkit/fundamentals/service-owner
- https://uit.stanford.edu/service-management/toolkit/problem
- https://uit.stanford.edu/service-management/toolkit/fundamentals
- https://uit.stanford.edu/service-management/toolkit/fundamentals/tech-ops-lead

### University of Minnesota OIT — incident targets, problem/RCA, monitoring, and maintenance

**Incident process.** OIT publishes four impact categories and incident response/resolution targets. Examples include **P1: 15-minute response and 4-hour resolution, 24×7**; **P2: 30-minute response and 8-hour resolution** under the page's business-hour/exclusion rules. Work is tracked in TeamDynamix. These are published service targets, not observed attainment percentages.

**Problem/RCA.** OIT describes problem records as appropriate after major incidents or recurring incidents and links problem resolution to change management or Known Error handling. Its RCA guidance describes gathering relevant teams after a major incident, identifying underlying causes, and producing corrective actions.

**Windows hosting operating example.** OIT's Windows hosting service guide documents:
- SCOM host ping monitoring that can page/email responders;
- disk space below **6 GB** resulting in a ServiceNow ticket;
- CPU above **95% for an extended period** resulting in a ServiceNow ticket;
- Zabbix encouraged for application-layer monitoring;
- events sent to Splunk;
- weekly full plus daily incremental backups, with typical **30-day** retention;
- weekly security scans;
- production maintenance commonly on the first Saturday/Sunday, with separate development and test windows.

The same guide separates OIT operating-system/agent responsibilities from customer application responsibilities. That boundary is useful when examining incident ownership and deployment accountability.

**Transferable use:** ask Iowa for severity definitions, response/resolution clock semantics, monitoring layers, alert routing, log aggregation, backup/restore evidence, maintenance windows, environment separation, and responsibility boundaries.

**Do not infer:** one hosting service guide is not evidence that all Minnesota services use identical tooling or thresholds, and the published incident targets are not observed performance.

Sources:
- https://it.umn.edu/services-technologies/resources/it-service-management-incident-process
- https://it.umn.edu/services-technologies/how-tos/tdx-problem-understand-use-problem
- https://it.umn.edu/services-technologies/how-tos/problem-management-how-perform-root
- https://it.umn.edu/services-technologies/how-tos/windows-server-hosting-service-guide
- https://it.umn.edu/services-technologies/teamdynamix

### University of Michigan ITS — current operational case evidence plus historical measured service data

**FY2025 accomplishment evidence.** Michigan ITS reports that System Operations added a redundant virtual cluster for network monitoring; Core Applications migrated Nagios users to Zabbix, standardized change control, reviewed disaster-recovery practices, and integrated its Major Incident group with OpsGenie. It also reports a storage migration of **more than 5 PB and more than 700 file shares** from October 2023 through March 2025, an automated monthly Linux security-patch framework, and upgrades of **more than 100 MySQL/RHEL servers** while collaborating with application owners and using replication to minimize downtime.

This is useful implementation/context evidence, but it is an accomplishments narrative rather than a controlled outcome study or institution-wide maturity measure.

**Historical MiWorkspace metrics.** A 2015 ITS article reported May–July 2015 service measures including **89.9% response within target**, **91.3% resolution within target**, and median incident durations by priority (Critical **0.4 h**, High **3.7 h**, Moderate **5.7 h**, Normal **4.6 h**). The article defines the service-level context, but the public material used here does not provide a raw denominator count for these percentages.

**Transferable use:** current case evidence can seed questions about monitoring-platform consolidation, change-control standardization, major-incident tooling, patch automation, large-scale migration coordination, replication, and application-owner involvement. Historical metrics demonstrate the need to preserve priority definitions and denominators before comparison.

**Do not infer:** 2015 MiWorkspace results are **not** a 2026 peer benchmark and should not be compared numerically with Iowa without normalized definitions and populations.

Sources:
- https://its.umich.edu/accomplishments/2025/administration/detail
- https://its.umich.edu/news/article/measuring-service-delivery-miworkspace-key-performance-indicators-kpis-1

### Cornell University IT — historical service-specific release and continuity operating agreement

Cornell's public **CornellAD Operating Level Agreement v1.4 (2010-06-07)** is intentionally treated here as a historical, service-specific example. It describes:
- a complete test Active Directory integrated with test Identity Management components;
- response targets of **≤1 hour for P1** and **≤1 day for P2**;
- standard maintenance windows of **5–7 a.m. weekdays** and **Sunday 6 a.m.–noon**;
- a change process that records purpose/impact, pre/post testing, backout, staffing, escalation, and NOC communications;
- patch sequencing through test and production with staged replication;
- service-continuity and disaster-recovery responsibilities;
- service-owner accountability;
- availability targets of no more than **3–4 hours of unplanned AD infrastructure downtime per calendar year** and no more than **2 hours for the Quest service**, subject to the agreement's scope/exclusions.

**Transferable use:** the document is a concrete example of release sequencing, environment isolation, rollback planning, communications, continuity, and service-level definition.

**Do not infer:** its 2010 targets are neither current Cornell enterprise benchmarks nor appropriate numeric targets for Iowa.

Source:
- https://it.cornell.edu/sites/default/files/Identity%20Management/CornellADOLA_v1_4.pdf

## 3. Transferable practice cards

### A. Risk-tiered release coordination

**Peer signal:** Stanford publishes risk-based lead times, CAB/ECAB handling, standard-change templates, and advance notice for extended maintenance.

**Iowa discovery questions**
- What change classes exist for ESS, RIS, and IAM?
- What evidence determines risk/impact and required review?
- Are lead times measured, waived, or overridden? How are exceptions recorded?
- Are collisions visible in a shared change calendar?
- What qualifies as emergency change, and is post-implementation review mandatory?

**Evidence to request:** recent normal/emergency change records, approval history, calendar extracts, failed/rolled-back changes, PIRs.

### B. Named service ownership and operational accountability

**Peer signal:** Stanford separates Service Owner, Service Manager, and technical operations responsibilities; Minnesota's hosting guide also separates platform and customer application obligations.

**Iowa discovery questions**
- Who is accountable for each ESS/RIS/IAM service outcome?
- Who owns technical health, on-call response, vendors, resilience, and backlog?
- Are ownership records current and tied to escalation paths?
- Where do central-platform responsibilities end and application-team responsibilities begin?

**Evidence to request:** service catalog, RACI/ownership records, escalation matrices, on-call documentation, vendor support boundaries.

### C. Environment and promotion controls

**Peer signal:** Cornell's historical OLA shows a complete test environment and staged test/production patching; Minnesota publishes distinct maintenance windows for production, development, and test.

**Iowa discovery questions**
- Which pre-production environments exist, and how close are they to production?
- What is the promotion path and who can bypass it?
- How are test data, dependencies, interfaces, and identity integrations represented?
- Are rollback/backout steps rehearsed and time-bounded?
- How are shared release windows coordinated across dependent teams?

**Evidence to request:** environment map, CI/CD or release runbooks, sample deployment records, rollback evidence, dependency inventories.

### D. Layered observability and alert routing

**Peer signal:** Minnesota's hosting guide spans host reachability, disk, CPU, application monitoring, and log aggregation; Michigan reports consolidating Nagios users onto Zabbix and integrating a Major Incident group with OpsGenie.

**Iowa discovery questions**
- What is monitored at infrastructure, platform, application, integration, and business-service layers?
- Which alerts page humans versus open tickets?
- How are noisy/redundant alerts suppressed or tuned?
- Do logs, traces, events, and service health share correlation identifiers?
- Are user-visible service degradations represented on a status surface?

**Evidence to request:** dashboards, alert rules, paging routes, top noisy alerts, sample correlated incident timeline, service-health reports.

### E. Major incident → problem → RCA → corrective action

**Peer signal:** Stanford and Minnesota both publicly link major/recurring incidents to problem management and RCA.

**Iowa discovery questions**
- What thresholds create a major incident?
- Who coordinates the incident and who owns restoration?
- When is an RCA required?
- How are contributing causes separated from root-cause claims?
- Are corrective actions tracked to completion and tested for recurrence?
- Is repeated incident history used to create problem records before another major event?

**Evidence to request:** anonymized postmortems, problem records, corrective-action backlog, recurring-incident analyses, closure criteria.

### F. Maintenance and stakeholder communication

**Peer signal:** Stanford publishes advance notice expectations for extended maintenance; Minnesota publishes maintenance windows and status notifications; Cornell's historical OLA includes NOC communications.

**Iowa discovery questions**
- What maintenance windows exist around academic, research, payroll, enrollment, or identity-critical cycles?
- Who can approve an exception?
- How are affected stakeholders identified?
- What is the notification lead time and channel?
- How are cross-service dependency impacts communicated?

**Evidence to request:** maintenance calendar, sample notices, dependency/contact lists, exception approvals.

### G. Metric semantics before benchmarking

A reliability metric is not comparable until all of these are known:
1. metric name and operational definition;
2. numerator;
3. denominator/population;
4. start/end period and timezone;
5. priority/severity definitions;
6. elapsed time vs business hours;
7. pending/customer/vendor/external time exclusions;
8. service/application boundary;
9. planned maintenance treatment;
10. data source and query;
11. target vs observed result;
12. statistic type (count, %, mean, median, percentile);
13. sampling/completeness assumptions.

The companion CSV records these distinctions explicitly.

## 4. Deployment benchmarking discovery matrix

| Topic | Minimum evidence from Iowa | Comparison gate | Useful peer context |
|---|---|---|---|
| Change success/failure | Change records, outcome definitions, rollback/recovery flags | Same definition of successful/failed change and same service boundary | Stanford change workflow |
| Change lead time | Created/approved/scheduled/deployed timestamps | Same clock semantics and change class | Stanford risk-tier lead-time policy |
| Deployment frequency | Production deployment events per service and period | Stable service population and comparable release granularity | Peer process examples only; no numeric norm asserted |
| Incident response | Priority definition, response clock, target and observed time | Same priority rules, business-hour treatment, and exclusions | Minnesota target definitions; Michigan historical observed data |
| Incident restoration/resolution | Start/end rules, pending time, service boundary | Same restoration vs resolution semantics | Minnesota targets; Michigan historical data |
| Availability | Measured interval, exclusions, dependency treatment, planned maintenance | Same service boundary and exclusion rules | Cornell historical target example only |
| Monitoring coverage | Inventory of critical components and active telemetry | Common definition of “covered” and current inventory | Minnesota layered monitoring; Michigan monitoring consolidation |
| Alert quality | Alert count, pages, actionable/duplicate/noise classification | Same observation window and routing rules | Discovery-focused; peer numeric benchmark unavailable |
| RCA follow-through | MI/problem count, RCA requirement, actions opened/closed | Same MI threshold and closure definition | Stanford/Minnesota process examples |
| Patch/release reliability | Patch population, success/rollback/exception counts | Same asset/application scope and patch category | Minnesota windows; Cornell historical staged release; Michigan current case evidence |
| Backup/recovery | Backup coverage, restore-test success, RPO/RTO evidence | Same data/service criticality and test definition | Minnesota service-specific backup practice |

## 5. What remains unknown until Iowa evidence is collected

Public peer evidence cannot establish:
- Iowa's actual deployment frequency, change-failure rate, MTTA/MTTR, availability, SLO attainment, alert quality, rollback rate, patch success, backup restore success, or corrective-action closure;
- whether ESS, RIS, and IAM share the same release, monitoring, incident, or ownership model;
- whether any published University policy is consistently implemented in those groups;
- whether a peer's target or tooling is appropriate for Iowa's constraints.

These should remain **unknown**, not scored by proxy.

## 6. Source register

| Organization | Source | Evidence class | Currency/period | Accessed |
|---|---|---|---|---|
| Stanford University IT | https://uit.stanford.edu/service/changemgt | Process description | current public page | 2026-09-19 |
| Stanford University IT | https://uit.stanford.edu/service/changemgt/leadtimes | Process/target description | page modified 2025-05-02 | 2026-09-19 |
| Stanford University IT | https://uit.stanford.edu/service-management/toolkit/fundamentals/service-owner | Role definition | current public toolkit | 2026-09-19 |
| Stanford University IT | https://uit.stanford.edu/service-management/toolkit/problem | Process description | page modified 2023-07-11 | 2026-09-19 |
| Stanford University IT | https://uit.stanford.edu/service-management/toolkit/fundamentals | Toolkit guidance | page modified 2026-06-30 | 2026-09-19 |
| University of Minnesota OIT | https://it.umn.edu/services-technologies/resources/it-service-management-incident-process | Process + published targets | current public page | 2026-09-19 |
| University of Minnesota OIT | https://it.umn.edu/services-technologies/how-tos/tdx-problem-understand-use-problem | Process description | page modified 2026-02-12 | 2026-09-19 |
| University of Minnesota OIT | https://it.umn.edu/services-technologies/how-tos/problem-management-how-perform-root | Process description | current public page | 2026-09-19 |
| University of Minnesota OIT | https://it.umn.edu/services-technologies/how-tos/windows-server-hosting-service-guide | Service-specific operating guide | page modified 2026-02-12 | 2026-09-19 |
| University of Michigan ITS | https://its.umich.edu/accomplishments/2025/administration/detail | Case/accomplishment evidence | FY2025 | 2026-09-19 |
| University of Michigan ITS | https://its.umich.edu/news/article/measuring-service-delivery-miworkspace-key-performance-indicators-kpis-1 | Measured outcome | May–Jul 2015; historical | 2026-09-19 |
| Cornell University IT | https://it.cornell.edu/sites/default/files/Identity%20Management/CornellADOLA_v1_4.pdf | Historical service-specific OLA | v1.4, 2010-06-07 | 2026-09-19 |

## 7. Assessment use

The defensible transfer is **practice pattern → Iowa question → Iowa evidence → locally interpreted finding**. It is not **peer number → maturity score**.

Recommended analysis sequence:
1. capture Iowa's actual service boundaries and metric definitions;
2. inspect raw artifacts for ESS, RIS, and IAM;
3. separate targets from observed results;
4. normalize definitions before any numeric comparison;
5. use peer practices to identify plausible control points and interview prompts;
6. label any remaining evidence gap as unknown;
7. recommend improvements from Iowa evidence and operating constraints, not from peer reputation or tool choice.
