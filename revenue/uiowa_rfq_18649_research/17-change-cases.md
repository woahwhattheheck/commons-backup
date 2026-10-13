# UIOWA-017 supplement: research-administration integration and change cases

**Status:** PUBLIC CONTEXT / PROPOSED DISCOVERY AID — not University of Iowa findings.  
**Prepared:** 2026-09-19 by ZZ-KESTREL-73 (GPT-6 Astra Pro).  
**Operation:** `uiowa-017-change-cases-kestrel73-20260919`.

This module supplies operational cases to the canonical UIOWA-017 peer pack; it does not replace that pack, select a formal peer cohort, recommend products, or assign maturity scores. The cases were selected for explicit descriptions of interfaces, workflow changes, and operating responsibilities, not institutional reputation. They are a purposive public-source sample, not a representative benchmark.

Read alongside the [source register](17-change-source-register.md) and [24-question interview matrix](17-change-interview-matrix.md). Source IDs resolve to exact URLs, sections, and date qualifications. All sources were accessed on **2026-09-19**; access date is not publication date.

## 1. Establish the service boundary before using a case

| Institution / selected service | Publicly described boundary | Boundary not transferable to Iowa |
|---|---|---|
| Michigan / eResearch Proposal Management (eRPM) | Proposal and award routing, unfunded agreements, and clinical-trial routing forms; governance involves research leadership, sponsored projects, a research-administration council, and ITS. [S01] | A routing form is not a clinical data platform. Neither the software inventory nor governance membership establishes Iowa RIS responsibilities. |
| Stanford / SeRA and its Cayuse interface | Sponsored-project administration from proposals through financial closeout; SeRA is described as the institutional sponsored-project record. [S04] | Do not infer a general laboratory, clinical, or research-data system boundary. The service description was last modified in 2023. |
| Washington / SAGE | Proposals, awards, budgets, advances, and subaward requests. [S07] | The selected cases concern award/finance interfaces. Other modules mentioned in release communications do not expand Iowa scope. |
| UNC-Chapel Hill / RAMSeS and ORIS | A collaboratively developed research-administration application within a broader research-administration support portfolio. [S10], [S11] | ORIS's wider portfolio is not the boundary of each application and is not evidence that Iowa RIS owns the same services. |

**Working inference:** an assessment can usefully follow a research-administration transaction across business-owner, application, identity, finance, and sponsor-facing boundaries. Which boundaries actually apply must be established with the Iowa service owner first. Public university web pages do not establish a staffing-size match, service performance, internal architecture, or actual adoption in Iowa.

## 2. Evidence vocabulary

**Published release account** means the institution reports a dated change; it is not independently witnessed production behavior. **Operating instruction** describes a documented user workflow, not its frequency or effectiveness. **Service description** states intended scope, not measured delivery. **Future-tense intent** is explicitly weaker than implemented integration. **Assessment design** below is our proposed inquiry, not a peer requirement.

No selected source supplies a comparable error-rate denominator, lead-time distribution, adoption rate, or controlled before/after evaluation. Consequently there is no numeric peer score, improvement percentage, percentile, or service-level target in this supplement.

## 3. Eight usable cases

### C01 — Sponsor-driven interface and validation change

**Boundary / date / evidence:** Michigan eRPM's sponsor-submission component; release account dated **2026-05-11**. [S03]

**Observed in the source:** SF-424 versions 10.10/10.10.1 added agency-form support, accommodated an alphanumeric Assistance Listing Number, and changed validation messaging for common-form attachments. [S03]

**Assessment design:** use one recent external specification change to inspect the complete path from notification to field mapping, test expectations, release acceptance, and user guidance. Ask whether a seemingly small type change reaches imports, search, exports, and downstream reports, not only the visible form.

**Evidence request:** an approved change record, source specification/version, representative redacted field mapping, test results, deployment decision, and affected-user communication. Trace one accepted and one rejected synthetic input through the documented expected behavior.

**Transfer limits:** sponsor packages and dates are local. A published release does not establish comprehensive regression coverage or successful submissions. The assessment should not prescribe these exact forms or validation rules to Iowa. **Interview rows:** Q01–Q03.

### C02 — Agreement intake and business authority move together

**Boundary / date / evidence:** Michigan eRPM unfunded-agreement intake and its contract-workflow handoff; release account dated **2026-07-20**. [S02]

**Observed in the source:** revised DUA/NDA intake requests more information, and CFRA can initiate specified Ironclad workflows while ORSP retains final review, approval, and signature. [S02]

**Assessment design:** separate authority to start a workflow from authority to accept its outcome. Inspect who maintains intake definitions, whose policy interpretation is used, and how application permissions correspond to the agreed business handoff.

**Evidence request:** a role-to-action map, approved intake change, redacted handoff example, acceptance criteria, and revised guidance. A data-category field is metadata about an agreement; do not infer that the application stores the underlying research dataset.

**Transfer limits:** neither these local categories nor this departmental split is an Iowa requirement. Public documentation does not prove access reviews, least privilege, or legal compliance. **Interview rows:** Q04–Q06.

### C03 — Queue state and historical meaning must survive changes

**Boundary / date / evidence:** Michigan award-change requests and deliverable tracking; release account dated **2026-07-20**. [S02]

**Observed in the source:** a new pending-contract-officer state distinguishes that queue from sponsor review; the historical request view retains the deliverable selection made at submission. [S02]

**Assessment design:** inspect whether reports and operator screens preserve what an earlier decision meant after a workflow or reference-data change. Distinguish an unresolved business decision from a failed technical transaction.

**Evidence request:** a state-transition definition, a before/after redacted example, a historical-record regression check, and the owner of each waiting state. Select an old record as well as a new one.

**Transfer limits:** a more descriptive state is not proof of shorter cycle time. A historical view is not, by itself, an immutable audit log. **Interview rows:** Q07–Q09.

### C04 — Linked systems still need explicit human reconciliation

**Boundary / date / evidence:** Stanford Cayuse-to-SeRA proposal transfer; **publication/update date not displayed** in the consulted guide; accessed 2026-09-19; operating instruction. [S05]

**Observed in the source:** the guide documents operator verification, partial field population, refresh behavior, manual updates, and avoiding duplicate subaward entries. [S05]

**Assessment design:** test the operational contract between linked applications. For each mapped field, identify the authoritative system, overwrite behavior, matching rules, and the operator responsible for unresolved differences. Treat a visible link as distinct from continuous synchronization.

**Evidence request:** an interface inventory, mapping and identity rules, a redacted reconciliation example, a documented exception path, and synthetic cases for missing values, duplicate entities, and changed values after initial transfer. No live patient, personnel, or award record is needed for this inquiry.

**Transfer limits:** these are vendor- and institution-specific instructions. They do not establish a measured duplicate rate or endorse automatic bidirectional synchronization. **Interview rows:** Q10–Q12.

### C05 — Release communication can expose data-history requirements

**Boundary / date / evidence:** Stanford SeRA administrative records; the release register includes **2025-10-10 (Dolomites)** and **2026-01-08 (Everest)** entries; published release accounts. [S06]

**Observed in the source:** the October entry describes attachment-version attribution and comment changes; the January entry reports subaward activity-tracking and other administrative updates. [S06]

**Assessment design:** connect the change log to the meaning of retained records. Ask how an analyst distinguishes the original evidence, a revised attachment, an edited comment, and a later administrative action without relying on filename alone.

**Evidence request:** approved record-version behavior, a synthetic revision sequence, migration/reconciliation results where relevant, and training or communication tailored to affected roles. Confirm retention decisions with the authorized records owner; do not infer retention rules from the software screen.

**Transfer limits:** dated public entries do not demonstrate release completeness, records-policy compliance, audit immutability, or that no intervening release occurred. **Interview rows:** Q13–Q15.

### C06 — Stabilization is a continuing workstream, not a binary milestone

**Boundary / date / evidence:** Washington SAGE modification-to-Workday integration; release account dated **2026-07-15**. [S09]

**Observed in the source:** UW reports fixes for modification errors involving advance-spend renewal lines and separately describes further work planned to reduce manual entry and expand validation. [S09]

**Assessment design:** separate shipped corrections from planned improvements. Follow an exception class from support observation to business-impact assessment, fix, acceptance test, and post-release monitoring. Identify who authorizes a manual completion when an interface cannot finish.

**Evidence request:** a redacted exception classification, a linked defect/change record, acceptance evidence, open follow-up items, and an agreed reconciliation procedure. Preserve planned items as pending until evidence of delivery exists.

**Transfer limits:** a reported fix is not a measured reduction in failure rate. Washington's finance configuration and transaction types are not assumed to exist in Iowa. **Interview rows:** Q16–Q18.

### C07 — Show operators enough detail to finish the business transaction

**Boundary / date / evidence:** Washington SAGE Central award setup/modification requests and Workday; release communication dated **2026-09-08**. [S08]

**Observed in the source:** the release adds integration success/failure details to assist Grant and Contract Accounting with integration completion or manual updates. [S08]

**Assessment design:** evaluate observability from the business operator's perspective: can a responsible person tell what completed, what remains, and who must act? Technical monitoring and transaction-level reconciliation answer different questions.

**Evidence request:** sanitized status examples, escalation responsibilities, correlation between request and downstream record, retry/manual-completion guidance, and a closed exception example. Test whether operators can recover without undocumented personal knowledge.

**Transfer limits:** more visible diagnostics do not prove shorter resolution time or complete telemetry. This case deliberately excludes the medical-screening retirement described elsewhere in the same release. **Interview rows:** Q19–Q21.

### C08 — Future-tense integration is an evidence gap, not implementation

**Boundary / date / evidence:** UNC RAMSeS within the broader ORIS portfolio; **publication/update dates not displayed** in the consulted pages; accessed 2026-09-19; service descriptions. [S10], [S11]

**Observed in the source:** RAMSeS is described as a collaboration among technical, sponsored-program, and campus stakeholders. Its compliance-integration description uses future tense; ORIS describes a wider administrative support remit. [S10], [S11]

**Assessment design:** tag statements as intended, demonstrated, or measured. Resolve scope through service ownership and current records rather than equating similarly named organizational units. A plan needs a delivery artifact before it becomes an implementation claim.

**Evidence request:** the actual service list, interface owners, current implementation status, a demonstration or accepted change record for an asserted integration, and an explicit list of excluded systems.

**Transfer limits:** no implementation date, completion claim, or performance measure is inferred. UNC's clinical/compliance relationships do not establish an equivalent Iowa responsibility. **Interview rows:** Q22–Q24.

## 4. Proposed interview use and evaluation

Start with Q22 to agree the RIS service boundary. Choose one recently completed change and one unresolved exception that span a confirmed interface. Use the relevant case's three questions rather than administering every question indiscriminately. Suggested interview roles are roles to invite if applicable, not assigned people or commitments.

For each answer, record the service, source artifact, relevant date/version, responsible role, observed behavior, unresolved contradiction, and next evidence request. Use four descriptive states: **not yet evidenced**, **documented intent**, **demonstrated example**, and **measured with a defined population**. These are evidence states, not a maturity scale. An absent public document or unavailable interview artifact is not automatically an absent practice.

For a voluntary local measurement, agree the period and denominator before counting. Candidate measures include reconciliation-required requests divided by eligible interface requests, or elapsed time from first exception to verified business completion. These are proposed definitions, not peer results. Report counts, excluded records, missing timestamps, transaction mix, and manual-work treatment. Do not pool unlike services or infer causality from a pre/post difference alone.

## 5. Integration with the assessment work

This supplement can inform software-development discovery through mapping and regression examples; security discovery through role boundaries and data-handling questions; and deployment/operations discovery through change acceptance and reconciliation. It does **not** supply evidence of peer or Iowa AI adoption. Any AI-readiness inquiry should start from the confirmed workflow, permitted data, human decision rights, and locally authorized evaluation criteria rather than projecting an AI use case onto the public examples.

Use the matrix as a proposed interview aid, not as findings fed into an authoritative scoring bundle. It changes no commercial terms, submission deadlines, scope commitments, or customer authority. Real engagement evidence must remain in an authorized private evidence location, not this public repository.

[S01]: https://its.umich.edu/academics-research/research/eresearch/proposal-management
[S02]: https://its.umich.edu/academics-research/research/eresearch/proposal-management/release-notes/1400338
[S03]: https://its.umich.edu/academics-research/research/eresearch/proposal-management/release-notes/1396939
[S04]: https://uit.stanford.edu/service/sera
[S05]: https://ora.stanford.edu/resources/sera-and-cayuse-user-guides-and-resources/linking-a-cayuse-proposal-to-a-pdrf
[S06]: https://ora.stanford.edu/resources/sera-system-releases-and-updates
[S07]: https://research.washington.edu/research/tools/sage/
[S08]: https://research.washington.edu/research/announcements/september-8-2026-sage-release-notes/
[S09]: https://research.washington.edu/research/announcements/july-15-2026-sage-release-notes/
[S10]: https://research.unc.edu/systems/ramses/
[S11]: https://research.unc.edu/oris/
