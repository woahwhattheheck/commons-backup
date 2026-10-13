# UIOWA-012 — Iowa policy applicability reference

**Status:** proposal / kickoff preparation only; public policy context, not an assessment finding or compliance determination  
**Prepared:** 2026-09-19  
**Access date for public sources:** 2026-09-19  
**Scope:** University of Iowa RFQ 18649 preparation for ESS, RIS, and IAM across software delivery, security, deployment/operations, and AI readiness.

The companion table, `12-policy-context.csv`, records clause-level source material, operational implications, discovery questions, and applicability caveats. This memo explains how to use those sources without treating published policy as proof of actual practice.

## 1. Evidence rule

Use University policy and technical standards to answer **what requirements or institutional expectations may apply**. Use interviews, sampled artifacts, system records, and observed workflows to answer **what ESS, RIS, and IAM actually do**.

A policy statement is therefore a **discovery anchor**, not evidence that:

- a control is implemented;
- a control is effective;
- a practice is consistent across services;
- a service is compliant;
- a group has a particular maturity level;
- an exception does or does not exist; or
- an application has a specific data classification.

Where applicability depends on data classification, service criticality, record type, technology type, or an approved exception, the assessment must obtain that fact from the accountable University role.

## 2. Current source register

| ID | Authority | Current public version/date used | Why it matters | Source |
|---|---|---|---|---|
| P01–P06 | IT Security Policy **IT-18** | Reviewed 2023-09-27 | stewardship/custody roles, access, separation of duties, production testing, change control, backup/recovery, DR | https://itsecurity.uiowa.edu/policies-standards-guidelines/security-policy |
| P07–P10 | Institutional Data Policy **IT-19** | Reviewed 2023-09-27 | classification, copied/propagated data, purpose-limited access, secondary use, backup responsibilities | https://itsecurity.uiowa.edu/policies-standards-guidelines/institutional-data-policy |
| P11–P12 | Enterprise Authentication, Authorization and Access Policy **IT-15** | Reviewed 2023-09-27 | enterprise authentication, local-auth exceptions, eligibility, privilege review, role-change deprovisioning | https://itsecurity.uiowa.edu/policies-standards-guidelines/enterprise-authentication-authorization-and-access-policy |
| P13–P14 | IT Accessibility Policy **IT-26** | Reviewed 2025-03-13 | lifecycle accessibility, third-party scope, procurement evaluation, documented exceptions | https://itsecurity.uiowa.edu/policies-standards-guidelines/itaccessibility |
| P15 | Standards for Accessible Technology | Web standard effective 2020-06-01 | WCAG 2.1 AA baseline for University web pages/sites/apps; separate non-web standards | https://itaccessibility.uiowa.edu/standards |
| P16–P18 | Policy Manual Ch. 17 — Records Management | Amended through 2022-03-31 | official vs transitory records, retention, disposal, holds | https://policy.uiowa.edu/administrative-financial-and-facilities-policies/records-management |
| P19 | Policy Manual Ch. 19 — Acceptable Use of IT Resources | Amended 2022-03-11 | institutional-system security, backup/recovery, operational logging/monitoring, records/public-request context | https://policy.uiowa.edu/community-policies/acceptable-use-information-technology-resources |

**Source hierarchy for this assessment:** current Policy Manual / IT policy text → University technical standards → implementation guidance. Guidance can clarify technique but must not silently widen a policy requirement.

## 3. Operational implications by assessment area

### Software development

1. **Production testing and change traceability.** IT-18 requires system/application software to be tested before production installation and requires change controls for systems handling non-public institutional data, including change request, approval, testing, and final implementation evidence.
2. **Role separation is contextual, not a checkbox.** IT-18 identifies separation of critical duties and specifically calls out developer/system/database administrator overlap unless authorized. The assessment should recover actual role maps and authorized exceptions, especially in smaller teams.
3. **Authentication belongs in design decisions.** IT-15 says locally developed software should use Enterprise Authentication when possible, while non-integrated services require review/transition consideration.
4. **Accessibility is lifecycle work.** IT-26 requires accessibility to be included through the software lifecycle. For web applications, University standards identify WCAG 2.1 AA as the technical baseline.
5. **Development data inherits data obligations.** Under IT-19, institutional data remains institutional data when copied or propagated. Test datasets, support exports, logs, backups, and analytics copies therefore need classification-aware discovery rather than a “non-production means non-sensitive” assumption.

### Security and access

1. **Authorization is tied to accountable roles and purpose.** IT-19 and IT-15 place non-public-data access decisions with Data Steward/Custodian responsibilities and limit use to the authorized purpose.
2. **Privilege lifecycle needs evidence of effect.** IT-15 expects periodic privilege review and account changes when roles change. The assessment should follow a sample from triggering event to effective change in target systems.
3. **People and service identities are different evidence lanes.** IT-15 separately addresses resource/service IDs and generic automated access. Assess ownership, purpose, privilege rationale, credential handling, review, rotation/expiration, and retirement without requesting credential values.
4. **Classification drives control applicability.** Do not infer Restricted/Critical status from an application name. Ask for the authoritative classification and steward decision.

### Deployment and operations

1. **Change control spans application, infrastructure, and cloud changes.** IT-18 explicitly includes physical hardware and cloud services for applicable change-control requirements.
2. **Recovery needs tested evidence.** Backup configuration is not the same as recoverability. IT-18 calls for sufficient backup/recovery and tested DR plans for systems critical to the University.
3. **Operational telemetry has governance context.** Policy Manual Ch. 19 acknowledges logging, monitoring, and backup as part of normal IT operations while also identifying privacy, legal process, discovery, and public-record considerations.
4. **Service criticality must be established, not guessed.** Recovery priorities, DR depth, and operational expectations should follow University-designated criticality and business needs.

### AI readiness

The current sources above do **not** establish that ESS, RIS, or IAM uses AI.

They do create useful discovery boundaries:

- IT-19 says data moved/copied/propagated remains institutional data.
- Access to non-public data remains purpose-limited.
- Secondary use of Restricted/Critical data is prohibited under IT-19; repurposing Public/University-Internal data requires the appropriate authorization.
- IT-26 means AI-enabled user-facing or authoring technology may still have accessibility responsibilities.
- Records policy may apply to AI-assisted decisions, outputs, approvals, or retained prompts/exports depending on their function as University records.

For any AI-enabled development or operational workflow, ask first about **purpose, data classification, authorization, retention, human review, output use, and system ownership**. Do not infer permissibility or prohibition from the generic label “AI.”

## 4. Kickoff / discovery questions

### Cross-cutting responsibility

1. For every in-scope service, who is the Data Trustee, Data Steward, and Data Custodian?
2. Which University policies/standards does the service owner consider directly applicable, and are there approved exceptions?
3. What evidence location is authoritative for requirements, approvals, change records, release records, access reviews, incidents, and service decisions?

### Delivery and change

4. Show one recent normal change and one urgent change from request through approval, testing, build/configuration, deployment, and post-change verification.
5. Which sampled services handle non-public institutional data, and how does that change the required change-control path?
6. Where do developer, administrator, database, release, and approval responsibilities overlap? Which overlaps are intentional and authorized?
7. What links the tested revision or configuration to the version actually deployed?

### Data and environments

8. What institutional data is present in development, test, staging, logs, backups, troubleshooting exports, analytics extracts, and CI artifacts?
9. Who assigned the data classification, and how does classification follow copied/derived data?
10. What data is reused for a purpose different from the original access grant? What authorization governs that use?

### Access and identity

11. Which applications use enterprise authentication and which use local/vendor authentication? What review/transition rationale exists for exceptions?
12. How are joiner/mover/leaver events propagated to repositories, pipelines, databases, service consoles, and support tools?
13. How often are user/service privileges reviewed, who defines the interval, and what evidence shows changes were completed?
14. How are nonhuman identities owned, approved, reviewed, rotated/renewed, and retired?

### Accessibility

15. For each user-facing application, what accessibility standard is used and where are test results retained?
16. Where is accessibility incorporated into requirements/design/development/release/maintenance?
17. For third-party technology, what procurement accessibility evidence, exception, or remediation plan exists?

### Recovery, logging, and records

18. Which services are designated critical? What is the latest recovery exercise and what did it actually prove?
19. Which operational logs/backups are necessary for security, recovery, service management, audit, or records obligations, and what access/retention rules apply?
20. Which delivery/security/incident/access artifacts are official University records versus transitory/convenience copies?
21. Which retention schedule entry applies to each official record category, and how are legal/audit/public-record holds propagated?

## 5. What the public sources cannot establish

The assessment must leave these **UNKNOWN** until engagement evidence supports them:

- whether a published control is currently implemented or effective;
- actual system/data classifications;
- actual ESS/RIS/IAM application and dependency inventories;
- current team structure, staffing, or role separation;
- source-control, CI/CD, test, approval, release, rollback, and monitoring practice;
- test-data contents or whether production data is copied into lower environments;
- current access-review cadence or deprovisioning latency;
- current service-account inventory or privilege scope;
- actual accessibility conformance or open accessibility defects;
- DR recovery objectives, last successful recovery, or dependency coverage;
- which engineering/operational artifacts are official records;
- exact retention period for a technical artifact without its record type;
- current AI use, model/tool inventory, or whether institutional data is used in AI workflows;
- compliance, certification, maturity, or comparative performance.

## 6. Suggested evidence requests

Keep requests narrow and representative:

- one responsibility map for each in-scope service;
- two recent changes per group (normal + urgent when available);
- one access joiner/mover/leaver sample and one service-identity sample per group;
- current application/data classification records for sampled services;
- current change-control procedure plus executed records;
- accessibility test/exception evidence for representative internally developed and third-party applications;
- one DR/recovery exercise packet for a designated critical service;
- sample access-review evidence;
- authoritative records-retention mapping for release/security/access/incident artifacts.

Do not request credentials, secret values, unrelated personal data, or bulk production datasets for this assessment.

## 7. Assessment usage rule

A report finding should keep three layers separate:

1. **Requirement/context** — what the cited University policy/standard says.
2. **Observed evidence** — what interviews/artifacts/samples actually demonstrate for a specific service/group and period.
3. **Interpretation/recommendation** — the practical improvement, with effort/dependency/owner assumptions stated.

This structure prevents the assessment from turning a policy reference into an unsupported compliance verdict and preserves a constructive, evidence-based scope.
