# UIOWA-011 — Iowa AIS institutional context map

**Status:** proposal / kickoff preparation only; public-source context, not assessment evidence  
**Prepared:** 2026-09-19  
**Access date for every source below:** 2026-09-19  
**RFQ context:** University of Iowa RFQ 18649 identifies Enterprise Student Systems (ESS), Research Information Systems (RIS), and Identity & Access Management (IAM) as assessment groups. This memo reconciles that scope to current public University descriptions without treating public pages as proof of internal practice.

## 1. Executive map

| Area | What current public University sources establish | Publicly visible interfaces | What remains unresolved for kickoff | Sources |
|---|---|---|---|---|
| Administrative Information Systems (AIS) | AIS is an ITS department. Current ITS and policy pages assign AIS responsibility for academic systems, HR systems, financial systems, research administrative systems, enterprise applications, identity/access management, enterprise data/reporting, and custom solutions/integrations. Ed Hill is listed as executive director of AIS and deputy CIO. | Functional university units that sponsor or use academic, HR, finance, research, workflow, identity, and data services; other ITS departments; OneIT. | Current internal group boundaries, staffing, portfolio ownership by application, operational handoffs, architecture, SDLC, release governance, observability, incident ownership, and decision rights are not established by these pages. | S01, S02 |
| Enterprise Student Systems (ESS) | Current University material describes AIS-ESS as supporting major academic administrative applications including MAUI, MyUI, and applications within ICON. A 2026 accessibility article names Bill Evanson as director of Enterprise Student Systems. Public examples show ESS building student/instructor-facing applications and working with other AIS teams and academic partners. | Office of the Provost, University College, Data/Analytics/Insights in AIS, instructors/students, accessibility functions, ICON-related services. | Exact ESS portfolio, team structure, engineering platform, production ownership, change calendar, release controls, on-call model, service objectives, backlog governance, and dependency ownership require direct confirmation. | S03, S04, S05 |
| Research Information Systems (RIS) | Current RIS pages say RIS supports research administration by delivering and maintaining integrated systems that reduce administrative burden, with primary focus on electronic research administration supporting the Division of Sponsored Programs and compliance units. A current OVPR page lists RIS as a reporting unit of the Office of the Vice President for Research. The RIS team page describes a director, a development team, production-application maintenance, second-tier support, and project leads working with business units. | OVPR, Division of Sponsored Programs, research-compliance units, administrative and IT partners, researchers/research staff/administrators. | Public sources do not resolve the complete present-day governance boundary between OVPR RIS and AIS research-administrative-system responsibility. Exact application inventory, hosting, source ownership, support tiers, shared infrastructure, release authority, security accountability, and escalation paths must be confirmed. | S06, S07, S08, S09 |
| Identity & Access Management (IAM) | ITS service pages state that ITS-AIS provides IAM services including account provisioning, authentication, and tools. Public services include Access Management, HawkID, Active Directory, Shibboleth/federation, directory lookup, and Duo two-step login. | Campus applications using HawkID/AD/Shibboleth; users and sponsoring units; electronic access workflows; service owners consuming authentication or group/access services. | The public catalog does not establish the full IAM system inventory, authoritative identity sources, joiner/mover/leaver workflows, privileged-access governance, service-account governance, recertification practice, dependency topology, or operational SLOs. | S10, S11, S12 |

## 2. Reconciliation to RFQ 18649

### 2.1 Treat ESS, RIS, and IAM as assessment boundaries, not inferred org-chart peers

The RFQ groups are useful interview and evidence boundaries, but the public University structure is not symmetrical:

- **ESS** is publicly described as an AIS group supporting major academic administrative applications (S03).
- **IAM** services are publicly attributed to **ITS-AIS** (S10, S11).
- **RIS** is currently listed as an **OVPR reporting unit** (S09), while University policy also assigns **research administrative systems** to AIS (S02).

**Kickoff implication:** do not infer that RIS reports through AIS, or that AIS owns every RIS application. Confirm whether responsibility is organizational, product-specific, infrastructural, co-managed, or split by lifecycle stage. The assessment should record actual responsibility per service rather than force the three groups into one presumed hierarchy.

### 2.2 Public service descriptions are context, not evidence of assessed maturity

Public pages show service purpose and examples. They do **not** establish whether current internal practice is effective, consistently followed, measured, automated, or mature. In particular, the following must come from engagement evidence:

- engineering workflow and source-control practices;
- code review, testing, dependency management, and release approval;
- environment management, CI/CD, rollback, monitoring, alerting, and incident learning;
- security design/review, vulnerability handling, secrets and privileged access;
- identity lifecycle governance and recertification;
- AI use in development/operations, model/data controls, human review, and evaluation;
- staffing capacity, work queues, service ownership, escalation, and performance measures.

## 3. Service / responsibility table for kickoff preparation

| Scope | Publicly described service or responsibility | University interface visible in public material | Kickoff question that turns context into evidence | Evidence strength | Sources |
|---|---|---|---|---|---|
| AIS | Academic administrative systems supporting admissions, financial aid, records, billing, advising, orientation, student success, faculty, and teaching/learning | Provost/academic administration and campus users | Which applications and shared platforms are in the RFQ scope, and which AIS group owns each lifecycle stage? | Current official org/policy description | S01, S02 |
| AIS | Research administrative systems supporting sponsored programs, research compliance, IRB, and animal care | OVPR, DSP, compliance units | Which research systems are AIS-owned, RIS-owned, or co-managed today? | Current policy description; boundary still ambiguous | S02, S07, S09 |
| AIS | Enterprise applications, data/reporting, custom software and integration services | Campus business units and other IT units | Which shared AIS platforms/integration services are dependencies for ESS, RIS, and IAM? | Current official org/service description | S01 |
| ESS | MAUI, MyUI, and applications within ICON | Students, faculty, academic administration, OTLT-related ecosystem | Confirm in-scope ESS application inventory, criticality, release windows, owners, and upstream/downstream dependencies. | Current 2026 University article | S03 |
| ESS | Student/instructor application delivery; SPOT example built with Provost/University College and AIS Data, Analytics, and Insights | Provost, University College, AIS data/reporting | How are product decisions, requirements, acceptance, data/reporting, and production support divided across partners? | University case study | S04 |
| ESS | Note Depot developed by AIS Enterprise Student Systems | ICON users, instructors, students, Student Disability Services-related use cases | What reusable platform, security, accessibility, AI, and support patterns from current ESS products apply across the portfolio? | Current ITS service description | S05 |
| RIS | Integrated research-administration systems intended to reduce administrative burden | DSP, compliance units, researchers, research staff, administrative staff | What is the authoritative in-scope RIS product list, and which business unit owns requirements/acceptance for each? | Current RIS mission/about pages | S06, S07 |
| RIS | Development team completes projects, maintains production applications, and provides second-tier support | RIS customers/business units; project leads | How are first-tier support, second-tier support, engineering, production operations, and escalation separated in practice? | Current RIS team description | S08 |
| RIS | Current OVPR reporting-unit placement | Office of the Vice President for Research | What is the current governance/interface with ITS/AIS for infrastructure, identity, security, architecture, deployment, and service management? | Current OVPR org page | S09 |
| IAM | Account provisioning, authentication, and tools | University applications and users | What are the authoritative identity sources and joiner/mover/leaver triggers for students, employees, guests, and affiliates? | Current ITS service description | S10 |
| IAM | Access Management, Active Directory, Shibboleth, HawkID, directory services | Application/service owners and campus units | Which services are systems of record vs integration/control points, and who owns authorization decisions for connected apps? | Current ITS service catalog | S10, S11 |
| IAM | Duo two-step login protects services including MyUI, ICON, Microsoft 365, and Employee Self Service | Major campus services | Which authentication assurance requirements vary by service, role, privilege, or data class, and how are exceptions governed? | Current ITS service description | S12 |

## 4. Boundary observations to validate in interviews

1. **AIS is broader than the three RFQ groups.** The assessment must avoid generalizing ESS/RIS/IAM evidence to all of AIS.
2. **ESS has visible cross-team delivery dependencies.** Public examples show collaboration with academic sponsors and other AIS functions; interview design should explicitly capture handoffs rather than assess ESS as an isolated engineering team.
3. **RIS has a governance boundary worth resolving early.** Current OVPR reporting plus AIS responsibility for research administrative systems means ownership must be mapped per system and lifecycle activity, not inferred from labels.
4. **IAM is a shared-service dependency, not only a standalone team.** Application teams may own authorization decisions while IAM supplies identity/authentication/group mechanisms; discovery should separate identity proofing, authentication, authorization policy, provisioning, and application enforcement.
5. **Public success stories are not maturity evidence.** Accessibility remediation, application launches, or published service descriptions can inform questions but cannot substitute for direct artifacts, samples, metrics, or interviews.

## 5. Minimum kickoff responsibility map to obtain

For every in-scope service/application, request one row containing:

- service/application name and business purpose;
- group owning product/business decisions;
- group owning code/configuration;
- runtime/hosting owner;
- deployment/release owner;
- security-review and vulnerability-remediation owner;
- IAM dependency and authorization owner;
- data owner/steward;
- monitoring/on-call/escalation owner;
- first-tier and second-tier support owner;
- material vendor/third-party dependency;
- current primary technical and business contact;
- critical academic/research calendar constraints;
- source repository / pipeline / runbook / service catalog references where permissible.

This single map prevents responsibility ambiguity from contaminating later maturity findings.

## 6. Public material cannot establish

Do **not** represent any of the following as known until engagement evidence supports it:

- actual headcount, allocation, contractor mix, or available capacity;
- current repository topology, branching model, CI/CD platform, test coverage, deployment frequency, change-failure rate, MTTR, uptime, or SLO attainment;
- actual production hosting/environment design or system dependency graph;
- actual vulnerability backlog, security exceptions, incident history, access-review results, or privileged-access inventory;
- actual use of AI by ESS, RIS, or IAM personnel;
- whether published policies and service descriptions are consistently implemented in day-to-day work;
- whether a public case study is representative of the broader portfolio;
- whether RIS applications are wholly owned by OVPR, AIS, or a shared model;
- whether named individuals on public pages remain the operational lead for every RFQ activity.

## 7. Source register

All sources are official University of Iowa pages and were accessed **2026-09-19**.

- **S01 — ITS Administrative Information Systems.** https://its.uiowa.edu/about-its/its-organization/administrative-information-systems
- **S02 — Policy Manual, Chapter 3: Information Technology Services and OneIT.** https://policy.uiowa.edu/services/information-technology-services-and-oneit
- **S03 — Accessibility: “UI makes progress to advance web, application accessibility” (2026-01).** https://accessibility.uiowa.edu/news/2026/01/ui-makes-progress-advance-web-application-accessibility
- **S04 — OneIT: “Developing a homegrown course feedback system.”** https://oneit.uiowa.edu/developing-homegrown-course-feedback-system
- **S05 — ITS service: Note Depot.** https://its.uiowa.edu/services/note-depot
- **S06 — Research Information Systems home / mission.** https://ris.research.uiowa.edu/
- **S07 — Research Information Systems: About Us.** https://ris.research.uiowa.edu/about-us
- **S08 — Research Information Systems: Our Team.** https://ris.research.uiowa.edu/node/56
- **S09 — Office of the Vice President for Research: Reporting Units.** https://research.uiowa.edu/reporting-units
- **S10 — ITS: Accounts and Passwords.** https://its.uiowa.edu/services/accounts-and-passwords
- **S11 — ITS: All Services / IAM-related service catalog entries.** https://its.uiowa.edu/service
- **S12 — ITS: Two-Step Login with Duo Security.** https://its.uiowa.edu/services/two-step-login-duo-security

## 8. Completion check

- [x] AIS, ESS, RIS, and IAM mapped using current official University sources.
- [x] Every institutional statement above is traceable to the source register with access date.
- [x] Interfaces with University units are separated from unverified internal operating practice.
- [x] RIS/AIS governance ambiguity is explicitly labeled rather than silently resolved.
- [x] Unknown internal operations are enumerated.
- [x] Kickoff questions convert public context into evidence requests without treating public material as assessment findings.
