# R-COMMERCIAL — NYSED RFP #144 OCUE modernization qualification

**Operation:** `nysed-rfp144-ocue-modernization-pz812-20260913`  
**State:** **HOLD — PARTNER / SOURCE-PACKET GATE**  
**Buyer:** New York State Education Department (NYSED), Office of College and University Evaluation (OCUE)  
**Procurement:** RFP #144 — Office of College & University Evaluation (OCUE) Modernization  
**Published:** August 17, 2026  
**Source-currentness check:** October 4, 2026 — [dated source record](nysed_rfp144_ocue_20261004/SOURCE_CURRENTNESS.md)  
**Proposal deadline:** October 27, 2026 at 3:00 PM Eastern Time  
**Anticipated contract term:** January 1, 2027 through August 31, 2032 (68 months)  
**Confirmed buyer budget:** **UNKNOWN**  
**Our proposed price:** none  
**Award / booked revenue:** none / $0  
**External contact, submission, registration, signature, spend:** none

## Decision

This is a real, current, potentially material software procurement, but the truthful disposition today is **HOLD**, not BID.

The official NYSED landing page establishes a single-contract procurement for a **Software as a Service (SaaS), Low-Code, Cloud-based, Forms Management Platform**, a 68-month anticipated term, a 30% subcontracting ceiling, an M/WBE compliance obligation, and an October 27 electronic-bid deadline. It also publishes the controlling RFP plus supporting attachments.

What is not yet established here is equally important: the controlling RFP/attachments have not been retained and source-bound in Commons, the buyer does not publish a dollar ceiling on the landing page, and this repo currently provides no evidence that TJLabs/woahwhattheheck owns or is an authorized reseller/implementation partner for a qualifying enterprise low-code SaaS forms platform. A greenfield software-services pitch is therefore not enough to claim prime-bid readiness.

The strongest plausible commercial road is **partner-first**: pair with a buyer-acceptable SaaS/low-code platform prime, or become a truthful implementation subcontractor to one, then compete on migration, workflow configuration, integrations, quality, and delivery. Because the solicitation caps subcontracting at 30% of total contract budget, the exact prime/subcontract structure must come from the controlling RFP before any offer is prepared.

## Primary-source facts

Controlling public landing page:

- https://www.nysed.gov/funding-opportunities/rfp-144-office-college-university-evaluation-ocue-modernization

**October 4 source check:** NYSED's indexed September 21 notice supplies the revised dates below. Direct capture of the landing page and RFP returned HTTP 502 error bodies. The [source record and exact capture metadata](nysed_rfp144_ocue_20261004/SOURCE_CURRENTNESS.md) preserve that unresolved document-custody gap; the promised Q&A is not treated as already posted.

The official page establishes:

1. **Buyer / office:** New York State Education Department, Office of College and University Evaluation.
2. **Requested solution:** SaaS, low-code, cloud-based forms-management platform.
3. **Award count:** one contract.
4. **Term:** anticipated January 1, 2027 through August 31, 2032.
5. **Subcontracting:** limited to 30% of total contract budget, including non-employee direct personal services and related incidental expenses.
6. **M/WBE:** bidders must comply with participation goals through one of the methods defined in the RFP.
7. **Questions:** bidder questions were due September 11, 2026. NYSED says a Q&A summary will be posted no later than October 6, 2026.
8. **Proposal deadline:** October 27, 2026 at 3:00 PM ET through NYSED's electronic submission road.
9. **Required proposal packages:** Submission Documents, Technical Proposal, Cost Proposal, and M/WBE Documents.
10. **Signature boundary:** documents requiring signature must use an accepted signed/e-signature method; a typed script-font name is not an acceptable signature.
11. **Published source packet:** RFP document, submission documents, workflow/as-is attachments, OCUE/PEPR as-is documents, report list, mainframe batch-process inventory, milestones/deliverables, functional/non-functional requirements, change-request form, cost proposal spreadsheet, and NYSED security policies.

The landing page does **not** state a confirmed procurement budget or ceiling. Any third-party dollar estimate remains non-authoritative and must not be repeated as buyer budget.

## Secondary discovery — corroboration only

Useful discovery records, but **not controlling contract authority**:

- CivicIQ: https://civiciq.com/public-rfp/nysed-office-of-college-university-evaluation-modernization-rfp-144-2026
- Govly: https://app.govly.com/public/opportunities/16971688
- Bid Banana: https://bidbanana.thebidlab.com/bid/tY2vMchDAJvB9Gjeicwr

Current secondary records indicate, subject to primary-document verification:

- the modernization replaces a decades-old Unisys mainframe and consolidates/integrates Access databases, web pages, network storage, and external/internal interfaces;
- evaluation may be 60 technical points, 30 financial points, and 10 demonstration points;
- staffing may require an account executive, project manager, and business analysts;
- reported participation targets are 17% MBE + 13% WBE and a 6% SDVOB goal.

These are **verification targets**, not proposal claims. Do not quote them externally until they are matched to current NYSED RFP/addenda/Q&A bytes.

Third-party pages currently publish conflicting AI-generated dollar estimates. Those estimates are explicitly rejected for revenue accounting here. **Confirmed buyer budget remains UNKNOWN.**

## Internal evidence / fit check

Fresh Commons code searches at claim time returned no matches for `OCUE`, `low-code`, or `forms management`.

That is not proof the fleet lacks every relevant implementation skill. It is proof that this packet cannot truthfully claim an owned low-code SaaS product, a specific OCUE solution, or prior OCUE delivery from current durable Commons evidence.

There is meaningful adjacent technical capability across owned software work: workflow/state machines, migration tooling, API/integration work, auditability, security-oriented fail-closed boundaries, data normalization, CI, and operational support. Those capabilities can support an implementation role, but they do **not** substitute for mandatory vendor/OEM qualifications, approved references, a compliant SaaS platform, or government-contract representations.

## Likely delivery architecture if a partner road is supportable

A credible implementation plan should be framed as configuration/integration/migration around a buyer-acceptable platform, not as a rushed greenfield replacement for an enterprise low-code SaaS product.

1. **Platform qualification** — bind every mandatory functional/non-functional requirement to a native capability, supported extension, or explicit gap; distinguish configuration from custom code.
2. **Identity / RBAC** — integrate NYSED-approved identity, least-privilege roles, separation of duties, administrative audit trails, and account lifecycle controls.
3. **Workflow migration** — model program registration, review, change-request, complaint, and related OCUE/PEPR flows as versioned state machines with explicit authorization and immutable transition evidence.
4. **Data inventory** — inventory mainframe, Access, web, network-drive, document, report, and batch-process sources before migration; bind each source to owner, schema, retention, sensitivity, and reconciliation plan.
5. **Deterministic migration** — extract to immutable staging manifests, normalize with repeatable transforms, load idempotently, and reconcile counts/hashes/key business totals before cutover.
6. **Integration boundary** — use documented APIs/event/webhook interfaces, idempotency keys, replay queues, bounded retries, dead-letter handling, and end-to-end reconciliation for internal/external systems.
7. **Forms / validation** — source-bound field definitions, server-side validation, versioned form schemas, draft/resume controls, attachment custody, and explicit submission receipts.
8. **Records / audit** — retention and disposition controls, searchable record lineage, export/readback evidence, and fail-closed handling for ambiguous or malformed records.
9. **Accessibility / security** — trace each NYSED security/accessibility requirement to test evidence and ownership before go-live rather than relying on vendor marketing claims.
10. **Reporting** — reproduce the official report inventory with requirement-to-output traceability and reconcile migrated historical reports against authoritative samples.
11. **Cutover** — parallel run where required, rollback criteria, immutable migration/cutover receipts, support escalation map, administrator training, and post-go-live defect/SLA reporting.

This architecture is an internal delivery model only. It is not a representation that any specific commercial platform meets NYSED requirements.

## Hard gates before BID

Move from HOLD to BID-READY only after all of the following are source-bound:

1. Full current RFP + any addenda + the Q&A scheduled for October 6, with publication/supersession order.
2. Mandatory responsiveness checklist separated from scored preferences and demonstration criteria.
3. Named qualifying SaaS platform plus documented authority to sell/implement/support it under the required commercial model.
4. Every required firm/key-person reference is real, comparable, consented for use, and satisfies any prime-only/state-sector/minimum-year gate.
5. Exact current M/WBE / SDVOB percentages and methods are confirmed and a truthful participation/waiver road exists.
6. Required NYS responsibility, tax, lobbying, insurance, security, accessibility, data-location, records, and contract forms can be signed truthfully by an authorized human/entity.
7. Every mandatory staffing role has a real proposed person/organization that meets the RFP's requirements.
8. Mainframe/Access/files/reports/batch jobs/interfaces are sufficiently inventoried to price and schedule migration without guesswork.
9. Attachment 10 obligations are mapped to platform + implementation controls with evidence owners.
10. Attachment 9 is understood; SaaS licensing, implementation, migration, support, subcontractor cost, incidentals, contingency, and change-request economics fit the exact pricing form.
11. Any required demonstration can show source-bound OCUE workflows without fabricated data or capabilities.
12. Owner-approved legal signer and submission road exist; no agent self-signing or invented attestation.

## Current RED / YELLOW / GREEN map

### GREEN — established from the official page

- real NYSED procurement and identifier;
- active proposal deadline of October 27, 2026 at 3:00 PM ET;
- one long-term contract;
- SaaS / low-code / cloud forms-management category;
- 30% subcontracting ceiling;
- required technical/cost/M-WBE submission packages;
- cost/security and requirement attachments exist publicly on the NYSED page.

### YELLOW — plausible fit, requires source or partner proof

- workflow/form implementation;
- legacy data migration;
- API/integration engineering;
- auditability / records / reconciliation;
- ongoing support and change work;
- reported technical/financial/demo weighting;
- reported MBE/WBE/SDVOB percentages and staffing roles.

### RED — not presently evidenced

- owned qualifying enterprise low-code SaaS forms platform;
- authorized OEM/reseller/implementation-partner status;
- compliant comparable references accepted by the RFP;
- exact NYSED-required certifications/insurance/vendor-responsibility posture;
- confirmed M/WBE/SDVOB fulfillment partners or approved waiver road;
- controlling Attachment 9 price model;
- confirmed buyer budget;
- owner-authorized signer/submission package.

## BID / HOLD / NO-BID decision tree

### BID-READY

Only when the primary packet/addenda/Q&A are bound, every mandatory gate above is evidenced, the platform/partner road is contractually real, references are usable, and Attachment 9 produces acceptable economics.

### HOLD — current state

Use HOLD while the procurement is open but one or more source/OEM/reference/compliance/price gates remain unresolved. Continue internal source recovery and partner architecture only; do not burn time drafting unsupported marketing prose.

### NO-BID

Move to NO-BID if the full packet establishes a mandatory prime-only gate that cannot be met truthfully; no acceptable platform/partner road can be contracted before the deadline; M/WBE/SDVOB or vendor-responsibility requirements cannot be satisfied; required references cannot be used; security/accessibility/data obligations cannot be met; or a responsive price cannot be built without fabricated assumptions.

## Time-to-cash

This is not a quick-cash lane. Even a winning proposal would pass through evaluation, possible demonstration/negotiation, contracting, and a planned January 2027 start. Treat it as a potentially material pipeline opportunity, not booked revenue.

Because bidder questions closed September 11, unknowns cannot be solved by an unauthorized late buyer contact from this lane. The next public evidence checkpoint is NYSED's revised Q&A posting date of October 6.

## Next authorized action

1. Recover and retain the RFP PDF/Word, Submission Documents, Attachments 6/7/9/10, and then the Q&A scheduled for October 6 from the official NYSED page.
2. Build a mandatory-vs-scored matrix and exact compliance checklist.
3. Identify a truthful prime/OEM/partner road and evidence the commercial relationship before any proposal narrative.
4. Resolve references, M/WBE/SDVOB, vendor responsibility, insurance, security, accessibility, and signer gates.
5. Only then build a cost proposal from Attachment 9 and request owner approval for any external account/submission/signature action.

Update this packet rather than creating a competing qualification for RFP #144.

## Boundaries

No NYSED outreach, question submission, portal/account creation, proposal submission, signature, pricing commitment, certification claim, partner commitment, spend, credential use, or provider mutation was performed by this lane.

The owner email-sending boundary and all existing external-representation rules remain in force. Internal analysis may name model/seat provenance; no outbound email is authorized by this qualification.

## Revenue truth

- Confirmed buyer budget: **UNKNOWN**.
- Third-party AI budget estimates: **discarded / non-authoritative**.
- Our proposed price: **none**.
- Award: **none**.
- Booked / collected revenue: **$0**.
- External contact/submission: **none**.
- Durable value delivered: source-custodied qualification, partner-first architecture, hard-gate decision tree, and a fail-closed road from public RFP to a truthful bid/no-bid decision.
