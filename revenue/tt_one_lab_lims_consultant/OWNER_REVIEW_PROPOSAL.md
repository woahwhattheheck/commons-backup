# TT ONE LAB+ Pandemic Fund Project — LIMS Consultant

**Owner-review proposal architecture — not authorized for buyer contact or submission**

This artifact is built from the Ministry of Health first-party tender page and the official RFP PDF for the **Engagement of a Laboratory Information Management System Consultant**. It turns the abandoned opportunity note into a usable qualification and proposal-production carrier without inventing credentials, references, availability, rates, travel costs, conflicts, or buyer acceptance.

## Current controlling facts

The Ministry of Health is procuring an **individual consultant, local or international**, for a **nine-month** assignment performed **in person and in country in Trinidad and Tobago** under the TT ONE LAB+ Pandemic Fund Project. The proposal deadline is **October 1, 2026 at 10:00 a.m. Trinidad and Tobago local time**. The official tender page, RFP cover, and proposal-submission section state `procurement@health.gov.tt`; the required subject is `Proposal – LIMS Consultant – TT ONE LAB+ Pandemic Fund Project`; proposal validity is at least 90 days.

The RFP contains a real source discrepancy that must remain visible. Its clarification section prints `procurement@heath.gov.tt` while the tender page, RFP cover, and submission section use `procurement@health.gov.tt`. The clarification section says requests must be received by **September 21, 2026**. This carrier does not silently correct the printed clarification address and does not authorize a clarification email. Any clarification action requires a separate, source-reviewed route decision and collision-safe outbound authorization.

The official PDF was rendered and its structured text was retrieved in this environment, but raw PDF bytes were not acquired here. `source_manifest.json` therefore keeps the raw SHA-256 null instead of manufacturing a digest.

## Qualification gate

The RFP makes the following owner evidence essential:

- bachelor's degree in Health Informatics, Computer Science, or a related field;
- at least five years of experience in data management or health informatics;
- availability for the nine-month engagement;
- ability to perform the assignment in person/in country in Trinidad and Tobago;
- evidence of relevant professional experience; and
- at least three relevant professional references.

The public repository does not establish those personal qualification facts. Code, project history, or model inference cannot substitute for them. The executable carrier accepts only opaque SHA-256 evidence receipts for degree, experience, availability, and references; it does not place reference names, emails, telephone numbers, CV details, or other private evidence in the public packet. Even a complete receipt set produces only `OWNER_REVIEW_PACKET_COMPLETE_NOT_SUBMISSION_AUTHORITY`, never an authorization to submit.

## Evaluation strategy

The RFP weights the response as follows:

| Evaluation area | Weight |
| --- | ---: |
| Academic and professional qualifications | 15 |
| Relevant experience | 20 |
| LIMS / health information systems experience | 15 |
| Cross-sector data sharing and integration | 10 |
| Understanding and methodology | 10 |
| Work plan and approach | 5 |
| Stakeholder engagement and training | 5 |
| Financial proposal | 20 |

The weights total 100. The first four technical evidence areas plus price carry most of the score, so the response should be evidence-heavy rather than padded with generic consulting prose. Owner evidence should be mapped to each score-bearing section with a private source receipt; unsupported claims remain absent.

## Technical approach

### 1. Inception, discovery, and operating model

At commencement, confirm the participating institutional owners, decision rights, current-state documentation, approved access paths, environments, and data-handling boundaries. Produce the inception report and work plan with delivery cadence, source systems, acceptance owners, dependency register, issue/escalation route, and evidence required for each milestone.

The discovery phase should treat the Ministry of Health, Ministry of Agriculture and Fisheries, The University of the West Indies St. Augustine Campus, the Trinidad Public Health Laboratory, CARPHA/TTLIMS focal point, and relevant technical teams as distinct stakeholders whose operating constraints must be reconciled rather than assumed identical.

### 2. Existing LIMS and data-sharing assessment

Inventory existing laboratory information flows, TTLIMS touchpoints, SOPs, policies, data definitions, referral pathways, user roles, integration mechanisms, reporting obligations, and operational failure modes. Separate observed facts from assumptions and identify where data exchange currently depends on manual, duplicated, delayed, or institution-specific processes.

The gap analysis should cover interoperability, identity and access, data quality, traceability, auditability, security, resilience, privacy, workflow ownership, operational support, and cross-sector governance. Tie each recommendation to an observed gap and named acceptance owner rather than creating an unbounded modernization wishlist.

### 3. TTLIMS adaptation and cross-sector integration

The RFP calls for support adapting/extending the existing TTLIMS platform so it can facilitate appropriate use by the Veterinary Diagnostic Laboratory and UWI while preserving cross-sector boundaries. Begin with interface and workflow discovery rather than assuming a replacement platform.

For each proposed adaptation, document the business event, source and target institution, minimum required data, authoritative record, validation rules, security classification, role/access requirements, error and retry behavior, audit evidence, rollback/recovery path, and acceptance test. Interface decisions should remain technology-neutral until the actual current systems and supported mechanisms are confirmed.

### 4. SOPs, policies, tiered access, and data governance

Create cross-sector SOPs and governance artifacts that make ownership and permitted use explicit. Cover data stewardship, change control, data-quality escalation, cross-institution reconciliation, access provisioning/review/removal, tiered permissions, audit review, referral handling, retention, incident escalation, and operational continuity.

Tiered access should follow work need and institutional authority, with least privilege and auditable approval. No public proposal artifact should contain production credentials, private network information, patient/laboratory records, or protected operational details.

### 5. Data collection and standardisation

Define a shared vocabulary for agreed laboratory and surveillance exchanges, including field semantics, identifiers, required/optional status, accepted values, units, date/time handling, validation, lineage, error reporting, and institutional source of truth. Standardisation should include testable examples and exception handling, not only a data dictionary.

Where institutional fields cannot be losslessly aligned, record the mismatch and governance decision rather than coercing data into a misleading common field.

### 6. Functionality audits and acceptance evidence

For adapted integrations and workflows, define acceptance scenarios before implementation. Each scenario should state prerequisites, input, expected output, audit evidence, failure handling, and owner. Audits should cover successful flows and degraded/error cases, including partial availability, duplicate messages, invalid values, authorization failures, timeout/retry behavior, and reconciliation after recovery.

A milestone is complete only when the buyer-designated acceptance owner can inspect the agreed evidence. This aligns with the RFP's payment basis of acceptance of deliverables without claiming any deliverable has already been accepted.

### 7. Training and sustainability

Build role-specific training around approved workflows. Training should include normal operation, exception handling, security/data-governance responsibilities, escalation, and evidence capture. Capture attendance and buyer-approved completion evidence only through buyer-approved systems during an actual engagement.

The sustainability handoff should include current SOPs, architecture/interface notes, data definitions, access/governance procedures, test evidence, known limitations, prioritized follow-on work, and clear operational ownership.

## Nine-month delivery schedule

The buyer's **price structure contains seven price rows**, but the TOR's **delivery schedule contains six milestones**. They are not interchangeable. In particular, the separately priced SOP/policies row and LIMS-adaptation recommendation row combine into one Month-4 delivery milestone in the TOR.

1. **Inception Report, Work Plan and Methodology** — within two weeks of commencement.
2. **Initial Assessment and GAP Analysis** of existing data-sharing policies, practices and LIMS across partner institutions — within two months.
3. **Submission and acceptance of Cross-Sector SOPs, Policies and Practices for Data Exchange and Recommendation for Adapting Existing LIMS System** — Month 4.
4. **Data Collection and Standardisation**, including population of relevant TTLIMS data collection tools — Month 7.
5. **End-User Training and Training Report** — Month 8.
6. **Final Report** covering achievements, challenges, conclusions and actionable sustainability recommendations — Month 9.

Maintain a short evidence/decision ledger throughout the assignment: completed, blocked, needs buyer decision, acceptance evidence, and next priority. That is an internal delivery proposal, not a representation that the Ministry has accepted any additional cadence.

## Mandatory commercial structure

The Ministry's price structure is mandatory and contains **seven rows**:

1. Inception Report, Work Plan and Methodology;
2. Initial Assessment and GAP Analysis;
3. Cross-Sector SOPs, Policies and Practices for Data Exchange;
4. Recommendations for Adapting Existing LIMS Systems;
5. Data Collection and Standardisation;
6. End-User Training and Training Report; and
7. Final Report.

The executable carrier requires exactly those seven buyer-named price rows. Each value is expressed in integer minor currency units under one owner-selected three-letter currency code, and the owner must explicitly confirm that the values form the intended all-inclusive offer. The carrier rejects missing rows, extra rows, lowercase/ambiguous currency codes, bool/int aliases, and implicit extras.

**No price is supplied here.** Rates, travel, accommodation, taxes/VAT treatment, subsistence, insurance, and any other cost assumption remain an owner decision. A secondary estimate or model-generated rate must not become an offer.

## Submission package checklist

Before an owner could review a final response for possible submission, the private evidence packet must contain:

- evidence receipt for the required degree;
- evidence receipt plus at least five years for required experience;
- at least three distinct reference evidence receipts;
- nine-month and in-country availability backed by an evidence receipt;
- conflict disclosure resolved from `UNKNOWN`;
- score-bearing LIMS/health-system, cross-sector integration, and training evidence where available;
- complete seven-row all-inclusive owner pricing in one currency;
- exact official submission mailbox `procurement@health.gov.tt`;
- exact required subject line;
- at least 90-day proposal validity; and
- evaluation time before the official deadline.

The public carrier stores only opaque evidence digests for personal/private credential material. It deliberately does not embed CVs, reference contacts, identity documents, or private correspondence.

## Red-team / truth boundary

The carrier fails closed on:

- self-attested degree or experience without an evidence receipt;
- fewer than three distinct reference receipts;
- nine-month/in-country booleans without a supporting availability receipt;
- missing or extra price rows;
- bool values masquerading as integer years/prices;
- wrong or normalized submission route;
- drifted subject or insufficient validity period;
- source-manifest transplant;
- owner-input/packet transplant or packet tampering;
- duplicate JSON keys and non-finite numbers;
- projection of seven price rows into seven milestones; and
- evaluation after the proposal deadline.

The PDF's `procurement@heath.gov.tt` clarification spelling remains evidence of the source conflict. It is never promoted into the submission route.

## Authority and current state

This carrier authorizes **research, internal qualification, proposal drafting, evidence packaging, and owner review only**. It does not authorize buyer contact, a clarification request, Muse selection, proposal submission, signature/certification, a pricing commitment, travel/spend, access to Ministry systems or data, contract acceptance, award, payment, cash, or revenue recognition.

Current posture with public repository evidence alone is **HOLD_OWNER_EVIDENCE** because the required personal degree, experience, references, nine-month/in-country availability, conflict statement, and owner-selected all-inclusive financial proposal are not established in public evidence. That hold is commercially useful: the technical response is submission-shaped while credential and pricing truth remains explicitly owner-controlled.
