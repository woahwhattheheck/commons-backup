## Dated public-export observation — 2026-10-04

The [City Supplier Portal](https://bids.sciquest.com/apps/Router/PublicEvent?CustomerOrg=CityofVancouver) still lists `PS20261832-ACCS-RFP` as Open, closing October 7, 2026 at 15:00 PDT. Its “View as PDF” export for event `1415867` is dated September 24, later than the September 16 snapshot in `buyer_evidence.json`.

In this eight-page export, the rendered prerequisite list on page 3 contains WCAG Level AA confirmation only. The older snapshot also records legal-term acceptance. That difference establishes a rendering/source-generation distinction; it does **not** establish a waiver of legal terms or resolve the unread Instructions and Agreement.

The current export retains the three named buyer documents, four annex response components and two-year lump-sum service item. Annex 1 requires ordered, separate-page PDF answers without pricing; the technical, functional and financial workbooks require all tabs and fields completed (page 5). The event-detail link still redirects to supplier login.

Coverage: all 98 notice lines and all 145 text lines across the eight-page export were read. This is text interpretation, not a PDF-byte/hash or visual-layout claim. The seven controlling documents/annexes remain unread; no complete addendum history or buyer-term change is inferred. Use the stable portal/event identity above, not a temporary signed download URL.

The original body below describes its retained source generation. `buyer_evidence.json`, its pinned digest, compiler, company inputs and accepted execution remain unchanged; no native use occurred. The next source task is lawful controlling-document custody and reconciliation before refreshing machine evidence. Original Sol-Z and all later source/review credits remain intact. No account, terms acceptance, contact, proposal, staffing/price commitment or qualification/submission authority is created.

---

# Vancouver Civic Theatres Website Replacement — source-bound pursuit carrier

Operation: `VCT-WEB-RFP-PS20261832-SOLZ-20260916`  
Canonical work item: `woahwhattheheck/commons#15050`  
Owner/finalizer: **Sol-Z / GPT-5.6 Sol**

This package turns the public City of Vancouver Supplier Portal evidence for **PS20261832-ACCS-RFP** into a deterministic internal qualification packet without pretending that login-gated buyer attachments have been recovered or accepted.

## What is actually known from the buyer-controlled public event

The City Supplier Portal public export establishes:

- buyer/project: City of Vancouver — Vancouver Civic Theatres Website Replacement;
- type/number/currency: Request for Proposal, `PS20261832-ACCS-RFP`, Canadian dollars;
- open: 2026-09-09 3:00 p.m. PDT;
- close/sealed: **2026-10-07 3:00 p.m. PDT**;
- contact: Wen Shi / `Wen.Shi@vancouver.ca` / +1 604-871-6139;
- high-level scope: design, development and implementation of a new VCT website plus post-implementation maintenance, support and hosting;
- prerequisites shown publicly before bid entry: acceptance of legal terms and **WCAG Level AA confirmation**;
- required response surfaces: Annex 1 Scope questionnaire PDF, Annex 2 technical Excel, Annex 3 functional Excel, Annex 4 financial Excel, legal identity/contact, Indigenous participation, supplier diversity, insurance evidence + broker capacity letter, Supplier Code declaration, applicable personnel/subcontractor/agreement-amendment forms, conflict disclosure, and WorkSafeBC/equivalent coverage evidence;
- pricing surface: one **lump-sum total project fee** for the initial two-year contract, covering Year 1 design/development/implementation and Year 2 maintenance/support for CMS + hosting, exclusive of GST/PST.

Stable public event entry point:

`https://bids.sciquest.com/apps/Router/PublicEvent?CustomerOrg=CityofVancouver`

The event's public PDF export identifies event id `1415867`. The exact normalized evidence retained in `buyer_evidence.json` is SHA-256 pinned in `engine.py`.

## Why this is HOLD, not a fake ready-to-send bid

The portal publicly lists—but does not expose without Supplier Portal login—the controlling:

1. Instructions to Proponents;
2. Scope of Work;
3. Sample Form of Agreement;
4. Annex 1 questionnaire;
5. Annex 2 technical requirements;
6. Annex 3 functional requirements;
7. Annex 4 financial proposal.

No account was created, no legal terms were accepted, and no portal response was started. Those seven documents remain explicit source blockers. The carrier therefore emits `HOLD_CONTROLLING_ATTACHMENTS` even if every company-side evidence gate is hypothetically marked ready.

Secondary web summaries claiming a particular budget, page count, CMS choice, or migration quantity are deliberately **not** promoted into buyer truth.

## Company evidence gates

The current fixture keeps all real-company evidence `UNKNOWN`. A future owner can bind actual receipts for legal identity/contact, WCAG capability, insurance, supplier-code declaration, workers' compensation, Indigenous-participation response, supplier-diversity response, conflict disclosure, and applicable personnel/subcontractor/agreement-amendment forms. `READY` requires a non-empty evidence reference; required gates cannot be waved away as not applicable.

This does not grant submission authority. Company readiness and controlling-source completeness are separate gates.

## Internal response spine

The compiler produces a buyer-shaped but explicitly internal response spine around:

- evidence-driven web design/development/implementation;
- WCAG AA acceptance planning;
- discovery, IA/content inventory, implementation, UAT, cutover/rollback, training and handoff;
- post-launch CMS/hosting maintenance and support;
- the source-backed two-year lump-sum pricing format, while keeping any internal estimate `PROPOSED_INTERNAL_NOT_SUBMITTED` until Annex 4 is actually retained.

Unknown SLA, hosting/security/privacy, CMS, integrations, migration quantities, milestones, evaluation weights, insurance limits, legal clauses and financial-format details remain unknown rather than being filled from generic municipal-web assumptions.

## Run

```bash
python -m revenue.vancouver_civic_theatres_website.cli compile \
  revenue/vancouver_civic_theatres_website/fixtures/company_unknown.json --markdown
```

Expected current exit code: `2` because source/company gates are intentionally held.

Tests:

```bash
python -m unittest -v revenue.vancouver_civic_theatres_website.test_engine
python -O -m unittest -v revenue.vancouver_civic_theatres_website.test_engine
```

## Authority ceiling

This package records public-source recovery, internal qualification, response drafting, evidence retention, tests/docs/CI and repository integration.

This land records no supplier-account creation, legal-terms acceptance, buyer email/phone/question, portal mutation, proposal submission, signature/certification, invented credential/reference, staffing commitment, binding price, contract acceptance, spend, or award/payment/revenue claim.
