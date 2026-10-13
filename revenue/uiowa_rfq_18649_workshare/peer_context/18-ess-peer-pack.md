# UIOWA-018 — Student systems peer operating context

**Prepared by:** ZZ-KESTREL-ESS18 / GPT-6 Astra Pro  
**Operation:** `uiowa-018-kestrel-ess18-20260919` · Commons issue #16090  
**Research access date:** 2026-09-19  
**Classification:** `PUBLIC_PEER_CONTEXT_NOT_IOWA_EVIDENCE`

## Purpose and use

This pack supplies sourced operating examples and discovery instruments for Enterprise Student Systems (ESS). It does not assess the University of Iowa. Public descriptions are useful for deciding what to ask and what evidence to request; they do not establish the local system inventory, actual practice, maturity, compliance, or service outcomes.

Use the [discovery matrix](18-ess-discovery-matrix.md) during preparation and the [source register](18-ess-source-register.md) to inspect original headings and date limitations. All interview roles, evidence requests, comparison rules and rehearsal cases below are **proposed analyst design**, not University requirements or confirmed assignments. The register contains machine-readable bibliographic metadata; the matrix includes machine-readable interview records. Neither is a payload for the existing assessment compiler.

The original workshare carrier and compiler remain unchanged; their original source and repair attribution remain with their authors. This addition owns only the peer research and discovery material for UIOWA-018. It makes no procurement recommendation, calendar appointment, client commitment, submission, or commercial claim.

## Cohort and evidence strength

This is a purposive, three-institution example set, selected for accessible official descriptions of student-administration delivery. It is **not** a representative sample, a ranked peer cohort, or a staff-size match. Comparable staffing, application count, transaction volumes, support hours, regulatory exposure, implementation age and sourcing model have not been established. Minnesota supplies a narrower public service-boundary example than the Michigan and Berkeley collections; breadth of accessible documentation must not become a maturity ranking.

Eight sources are official IT/SIS pages. One Berkeley Registrar page is explicitly supplementary functional context. The evidence classes are published service/responsibility descriptions, governance or communication descriptions, a dated meeting notice, a planned maintenance schedule, and a calendar directory. None of the nine retained sources supplies a measured reliability result or a demonstrated recovery record. Publication/update dates are unknown where not stated; access dates, notice dates and planned event dates are kept separate.

## Peer cards

### Michigan — distinguish functional ownership from application delivery

**Boundary.** ITS describes M-Pathways Student Administration as an integrated student-administration information source shared across Ann Arbor academic and administrative units. Its module descriptions include student records, a Student Financials/Financial Aid interface, and demographic information spanning student administration and HRMS. This is a service description, not evidence of data accuracy or interface reliability. [ESS18-S01](https://its.umich.edu/enterprise/administrative-systems/m-pathways/student-administration-system)

**Operating example.** The curriculum description assigns course information maintenance to the Registrar and class information to departments. Classes are term-specific; described functions include enrollment limits, restrictions and data-verification reports. That distinguishes business-data/configuration changes from application code releases; it does not define an IT freeze period. [ESS18-S02](https://its.umich.edu/enterprise/administrative-systems/m-pathways/student-administration-system/curriculum-module)

**Coordination example.** The SRCAA page describes a Registrar-chaired stakeholder forum, two-way school/college representation, input on both system and manual-process improvements, monthly meetings, agendas and minutes. These are published arrangements, not proof of attendance, representative participation or completed decisions. [ESS18-S03](https://its.umich.edu/about/advisory-groups/administrative/srcaa)

**Dated communication evidence.** Unit Liaisons are described as a two-way central-administration communication route with meetings scheduled every two months. The index retains May and July 2026 cancellation notices and a September 9, 2026 meeting entry. These establish published notices, not a failure of the liaison model or a meeting completion record. [ESS18-S04](https://its.umich.edu/enterprise/administrative-systems/unit-liaisons) The September notice includes a tentative ERP-modernization agenda and Q&A route; it is not minutes or evidence that modernization shipped. [ESS18-S09](https://its.umich.edu/enterprise/administrative-systems/unit-liaisons/announcements/september-unit-liaison-meeting-1)

**Proposed transfer to discovery.** Trace one term-specific change from functional request through implementation, communication and verification. Identify who owns the policy decision, data/configuration edit, software change and post-change business check. Ask how urgent information reaches affected units when a standing forum is canceled. A different Iowa organization or asynchronous workflow may achieve the same outcome; the committee name and cadence are not requirements.

### Minnesota — make the integration and testing boundary explicit

OIT's Enterprise Applications page places admissions, registration, student financials and financial aid within Campus Solutions; lists finance and HR applications separately; describes integrating enterprise applications including Student Registration; and states that OIT maintains the systems and helps analysts/technology staff reach test environments and related information. The page does not establish the completeness of integration tests, environment fidelity or operational performance. [ESS18-S05](https://it.umn.edu/resources-it-staff-partners/enterprise-applications)

**Proposed transfer to discovery.** Ask for a dependency map around one student journey and the corresponding test-environment versions and ownership. Separate shared infrastructure responsibility, application responsibility and functional acceptance. Do not assume Iowa uses the same product, architecture, campus scope, shared-service boundary or ownership split. A test-environment link is a discovery lead, not proof that representative tests were executed.

### Berkeley — plan for a service chain, not just a screen

The SIS site describes a technology/administrative team that designs, configures, tests and maintains integrated student academic/financial systems, including CalCentral. Campus Solutions and CalCentral are described as supporting academic/administrative processes such as enrollment and student financial activity. This is the team's stated scope, not measured quality. [ESS18-S06](https://sis.berkeley.edu/)

The maintenance page names Campus Solutions, CalCentral and SIS APIs as affected surfaces. It anticipates up to four hours of weekday downtime within stated business hours and lists a future October 4, 2026 maintenance date with October 11 as its deferral. The duration is a planning statement, not an SLA, recovery objective or observed outage duration. No timezone is inferred. Past entries on the same page are not treated as completed maintenance records. [ESS18-S07](https://sis.berkeley.edu/maintenance)

The Registrar separately publishes a directory distinguishing enrollment, academic and examination calendars; enrollment deadlines are described as periodically updated. This supplies functional calendar context, not an IT change policy. The retrieved pages do not establish that a particular maintenance date was selected because of a particular academic deadline. [ESS18-S08](https://registrar.berkeley.edu/calendars/)

**Proposed transfer to discovery.** Follow a maintenance decision through its affected applications, APIs and consumers, including a deferral. Ask who rechecks dependency readiness and affected business deadlines after the date changes. Establish functional transaction/data verification after restoration, rather than treating an available portal as proof that every dependent process has recovered. Do not copy Berkeley dates, duration expectations or products into an Iowa recommendation.

## Calendar constraints are not maturity scores

The following is a proposed comparison method. A calendar-driven constraint describes when a student process matters and the consequences of delay. Maturity describes how consistently the relevant practice is performed and supported by evidence. A long freeze, frequent releases, a committee, or more automation does not by itself establish either a strong or weak practice.

| Comparison question | Context to retain | Evidence that would make the comparison useful |
|---|---|---|
| When is change unusually consequential? | Local registration, grading or other actual deadlines; affected population; exception paths | Versioned business-calendar source and a change decision referring to it |
| What type of change is involved? | Business rule, configuration, code, interface, infrastructure or data correction | One traceable change record with scope and accountable roles |
| Can a planned date move safely? | Consumer dependencies, notice obligations and business timing | Deferral decision, revised communications and repeated readiness checks |
| Is the same outcome achieved differently? | Manual, automated, vendor-delivered or shared-service implementation | Evidence of execution and verification, not tool names or diagram polish |
| What is missing from the sample? | Unseen services, exceptional periods or unrepresented roles | Coverage statement and a bounded follow-up request, not a fabricated score |

No retrieved source establishes a universal academic-cycle IT freeze rule. Do not infer a rule from a maintenance date and a separate calendar. Instead, investigate whether the local decision process considers relevant business timing, dependencies and exception handling. A necessary urgent repair during a busy period can be appropriate; its justification and verification matter more than adherence to an invented blanket rule.

## Continuity and measurement limits

The collection contains no observed recovery duration, restore-test result, verified data-reconciliation outcome, availability denominator or change-failure rate. Berkeley's linked service-level-agreement document could not be read: the destination returned HTTP 401. No SLA terms were extracted. Non-retrieval is not evidence that a peer lacks an agreement, recovery testing or a mature practice.

For an eventual local continuity assessment, request a redacted plan **and** a dated execution example for the same service/version. Compare detection, decision, restoration and business-verification timestamps only when their meanings, timezone, observation period and missingness are known. Label simulations, planned targets and production observations separately. These are proposed evidence requests; no such Iowa records were collected here.

## Turn context into an evidence-backed local observation

First confirm that the proposed question concerns an actual in-scope Iowa service and responsible role. Select a routine and an exception example where available, retaining the selection rationale. Record the source version, locator, period, service boundary and whether the account is a statement, a plan or an executed example. Preserve conflicting accounts and incomplete coverage.

A supported strength would describe a demonstrated practice within that exact sampled boundary. A potential gap needs a defensible expected outcome and supporting evidence, not simply a missing public page. Missing records support an unresolved evidence request until their absence and significance have been investigated. A single shared dependency should not be counted as three independent observations merely because several groups use it.

The peer cards remain background references. Do not relabel them as Iowa supplied evidence, place their source IDs in a local evidence-authority bundle, or use them to populate assessment maturity/confidence. Any later local finding must point to the locally gathered evidence and its own provenance. Public bibliographic links can accompany an explanation of a proposed practice without becoming proof that the practice exists locally.

## Immediate analyst handoff

Open the matrix, choose questions relevant to the confirmed service sample, and record unanswered applicability questions. Use the three fictional cases to check whether assessors preserve the difference between a plan, an executed example and a conclusion. Before using a time-sensitive source in a proposal or engagement, reread it and append a new access/version record rather than overwriting the historical research date. Nothing in this pack schedules that review or authorizes contact with a University or peer representative.
