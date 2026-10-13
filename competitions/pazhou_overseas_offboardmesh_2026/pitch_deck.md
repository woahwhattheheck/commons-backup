# OffboardMesh — 8-minute pitch deck script

## Slide 1 — Close a client without losing control
**OffboardMesh** is an AI-assisted client-offboarding control plane for service businesses. The AI proposes; deterministic controls bind caller-asserted evidence; the human owner reviews and executes approved actions outside the system.

## Slide 2 — The failure mode
Client closeout spans credentials, SaaS access, files, assets, recurring charges, contracts and final documentation. A generic chatbot can generate a checklist, but it cannot prove which source authorized an action or safely distinguish a suggestion from a destructive instruction.

## Slide 3 — The product
Caller-asserted evidence → model proposal → evidence binder → authority firewall → tamper-evident owner-review packet → human execution outside the system.

The executable emits one intentionally conservative review state: `OWNER_REVIEW_REQUIRED`. Model suggestions remain `PROPOSAL_ONLY`, and every task has `executionAuthorized:false`.

## Slide 4 — Why AI, why deterministic control
Models are good at interpreting varied source materials and proposing structured work. Deterministic code is better at authority ceilings, freshness, digest binding and replay. OffboardMesh combines them instead of asking one component to do both jobs. The current carrier does not authenticate evidence provenance; it labels that boundary `CALLER_ASSERTED_UNVERIFIED`.

## Slide 5 — Built, not just described
The Client Offboarding Desk core is shipped at `smb-showcase-inventory@1d851fae…`; its bounded commercialization carrier is live at `321d25de…`. This Pazhou carrier adds a runnable synthetic model-proposal/evidence demo, hostile tests, receipts, a rubric-gap audit and a submission-ready plan. No customer, revenue or organizer score is claimed.

## Slide 6 — Initial buyer and offer
ICP: MSPs, agencies, consultancies and professional-services operations.

Proposed entry sprint: USD 4,000 fixed / one legal entity / up to 25 engagement packages / 10 business days. Optional USD 750/month review cadence only after separate acceptance. Pricing is a hypothesis, not accepted revenue.

## Slide 7 — Defensible wedge
- generative model can never mint execution authority;
- task-level binding to caller-asserted evidence digests, with `ownerEvidenceBound:false` until an independent owner-authority boundary exists;
- current-vs-historical freshness semantics;
- opaque identifiers / no durable contact routes in the review packet;
- model-provider portability;
- receipts plus canonical compiler correspondence make the exact review state replayable.

## Slide 8 — 90-day path
30 days: one consented design-partner proof and baseline metrics. 60 days: buyer-approved model adapter + override/failure measurements. 90 days: one vertical template + repeatable deployment + second controlled pilot.

## Slide 9 — Risks are explicit gates, not footnotes
Hallucination → proposal only. Missing or malformed evidence → compile/review blocked. Destructive action → owner execution outside the system. Stale evidence → current verification fails while exact historical replay remains available. Legal/privacy ambiguity → owner/legal review.

## Slide 10 — What we want from Pazhou
Pressure-test the product with international operators, secure design partners and deployment feedback, and convert a shipped control primitive into a repeatable cross-border AI operations product. Registration/team facts remain owner-supplied; no traction or award is pre-claimed.
