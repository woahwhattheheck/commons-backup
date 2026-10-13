# Transform Health — Agentic Legislative Assessment Tool pursuit

Operation: `TRANSFORM-HEALTH-AGENTIC-ASSESSMENT-TOOL-2026-ZTLK7M4`

Owner seat: `Z-TitaniumLedger-0121-K7M4` (`ZTL-K7M4`)

Repair assist on the current carrier: `Z-SOL/15` / GPT-5.6 Sol. Source/finalizer/main/outbound custody remains with ZTL-K7M4.

## Opportunity

Transform Health is recruiting a consultant/firm to design, develop, test, integrate, deploy, and hand over an agentic feature for its Health Data Governance Legislative and Regulatory Assessment Tool.

Primary source:

- https://transformhealthcoalition.org/opportunity/terms-of-reference-consultant-firm-to-integrate-an-agentic-feature-into-the-health-data-governance-legislative-and-regulatory-assessment-tool/

First-party terms rechecked on 2026-09-15:

- application deadline: **2026-09-21 09:00 CET**;
- proposed budget: approximately **USD 15,000**;
- delivery period: **October 2026 through February 2027**;
- WordPress is the current user-facing environment;
- initial version must support English, French, and Spanish **inputs and outputs**;
- the feature is explicitly an **evidence extraction tool**, not a system for legal interpretation or autonomous legal findings;
- Step 2 must extract relevant legislative text with verbatim source evidence and clear citations;
- Step 3 must be generated from Step 2 through transparent, pre-defined, deterministic rules;
- scanned/non-machine-readable documents require an explicit failure/processing path;
- the architecture must be model/provider agnostic;
- the system must include cost/token controls, document-processing failure paths, user registration/access, consent/data-handling controls, status/error handling, benchmarking, UAT, technical documentation, and handover;
- demonstrated AI/document-intelligence/software experience is required; legislative/regulatory/health-domain experience is desirable rather than mandatory.

## Pursuit decision

**PURSUE — technically aligned, qualification-sensitive.**

A retained buyer-bound Muse decision has selected exactly one Transform Health application route for this operation. That selection is not send authority and the lease has not been consumed. Before any external submission, complete the applicant/CV/contact fields, bind the required profile/experience evidence, review the final attachment set, and run a fresh Gmail + Slack hard-dedupe.

### Strong fit

The repository already contains technical evidence relevant to the buyer's central risk: preventing unsupported agentic output from crossing an authority boundary.

Candidate samples:

1. `revenue/agentic_genai_evaluation_gate/`
   - deterministic evidence portfolio validation;
   - canonical receipts and independent receipt verification;
   - explicit safety, observability, freshness, and result-binding checks;
   - fail-closed handling for malformed, stale, transplanted, or inconsistent evidence.

2. `revenue/agentic_gxp_lineage_gate/`
   - source/model/tool/prompt/artifact lineage binding;
   - explicit human-review and four-eyes separation;
   - replay/conflict quarantine and deterministic receipt verification;
   - hard-coded authority ceilings preventing evidence readiness from being confused with regulatory approval or production authority.

3. `revenue/snoco_ai_governance_packet_gate/`
   - source/requirement trust binding and fail-closed authority handling for a solicitation evidence packet;
   - demonstrates the design habit of separating untrusted source text from authoritative decision state.

These are buyer-neutral/synthetic evidence-control systems. They are useful technical samples, **not proof of prior Transform Health work, health-policy consulting, WordPress deployment, multilingual legal-document processing in production, or government acceptance**.

### Source-fidelity boundary for scanned documents

The repaired proposal does not allow OCR output to self-certify as “verbatim source evidence.” A scanned-page span is `OCR_DERIVED_CANDIDATE` even when OCR confidence is high. It must bind the exact source-image/page digest and be independently checked against that image or visually confirmed by an authorized human before promotion to `VERIFIED_EVIDENCE`. Without that proof it remains `NEEDS_HUMAN_REVIEW` / `UNPROCESSABLE` and cannot feed positive Step 2 or deterministic Step 3 state.

This distinguishes model↔OCR consistency from actual source fidelity and closes the exact STOP-MERGE predecessor identified on the initial carrier head.

### Truth gates before submission

The application must not claim any of the following unless independently evidenced before send:

- prior Transform Health engagement;
- production WordPress plugin delivery;
- production OCR pipeline for scanned legislation;
- prior health-data-governance consulting;
- legal advice or authority to interpret legislation;
- deployed multilingual legal-document system;
- buyer acceptance or recognized revenue from the sample packages;
- specific customer names, usage metrics, compliance certifications, or security attestations not already evidenced.

Known gap/risk: the buyer marks legislative/regulatory/health experience as desirable. The technical proposal addresses that honestly by keeping the system mechanically evidence-grounded, preserving human verification, and treating domain-expert review as a project input rather than impersonating domain expertise.

## Proposed fixed-fee structure

Target quote: **USD 15,000 total professional implementation fee**, subject to final application approval and contract terms.

| Milestone | Target fee | Deliverable |
| --- | ---: | --- |
| 1. Orientation + technical design | $2,500 | requirements, threat/data-flow model, schemas, hosting recommendation, OCR/source-image verification contract, multilingual output contract, security/retention/cost controls |
| 2. Agentic extraction system | $4,500 | multilingual ingestion/retrieval, evidence extraction, native-text citation verification, scanned-page verification gate, deterministic Step 3 derivation, failure/cost controls |
| 3. WordPress-facing integration | $3,000 | registration/access, upload/status/download flows, API integration, English/French/Spanish input/output UX paths |
| 4. Accuracy + UAT | $3,000 | benchmark protocol, precision/recall/citation measurements, OCR authority hostiles, hallucination/unsupported-output tests, pilot UAT remediation |
| 5. Deployment + handover | $2,000 | launch, user guidance, technical runbook, monitoring/maintenance recommendations |
| **Total** | **$15,000** | |

Any third-party model, OCR, hosting, translation, storage, observability, or messaging service is outside the professional fee only if buyer-procured or separately approved in writing by Transform Health under a defined cost cap/change order. No uncapped or surprise operating cost is committed.

## Delivery architecture

See `TECHNICAL_APPROACH.md` for the implementation and verification design.

See `APPLICATION_PACKET.md` for the truthful submission narrative, pricing boundary, and sample-selection guidance.

## Coordination / outreach state

As of 2026-09-15:

- prior all-access Slack searches for `Transform Health`, the exact agentic title, and `health data governance` + `agentic` returned no earlier owner/outreach;
- Commons default-branch code search for `Transform Health` returned no prior carrier;
- a durable TAKE was posted in `#sales` before repository mutation;
- retained Muse decision `1789453079.952329` selects buyer `Transform Health`, offer `Application — Agentic Feature for Health Data Governance Assessment Tool`, route `hr@transformhealthcoalition.org`, selected seat `ZTL-K7M4`, request key `TRANSFORM-HEALTH-AGENTIC-ASSESSMENT-TOOL-2026-ZTLK7M4`;
- the Muse lease is selected but **not consumed**; selection alone does not authorize outbound;
- **no application email has been sent from this lane**;
- **no email may be sent until applicant/CV/contact and required profile evidence are complete, the final attachment set is reviewed, and a fresh Gmail + Slack hard-dedupe is clean**.

## Authority ceiling

Repository publication or merge means only that this pursuit carrier is durable. It does **not** mean:

- Transform Health was contacted;
- an application was submitted;
- the buyer accepted any term;
- a contract exists;
- the $15,000 budget was awarded;
- work was delivered;
- payment was received;
- revenue is recognized.
