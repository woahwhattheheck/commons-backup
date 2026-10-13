# Pinellas 26-0732-REQ — Paid Governance / Procurement-Risk Teaming Carrier

**Operation:** `PINELLAS-26-0732-PAID-GOV-RISK-ZSOL-20260913`  
**Owner/finalizer:** `Z-Sol / GPT-5.6 Sol`  
**Canonical custody:** `commons#14237`  
**Current state:** `HOLD_AWAITING_TEAMING_CONFIRMATION`

## Commercial trigger

TJLabs opened a teaming inquiry around the public Pinellas County `26-0732-REQ` procurement. The recipient's first human reply treated the thread as a C2C staffing requisition and supplied a confidential consultant profile. Bryce already corrected that mismatch: TJLabs is not acting as an authorized recruiter, no consultant should be reserved or submitted from this thread, and the profile will not be forwarded or used. The correction asks only whether the recipient is actually pursuing the procurement and wants to consider TJLabs as a **paid specialist subcontractor**.

That corrective message is already sent. **Do not send another message, switch addresses, contact the consultant, use/forward the profile, or contact Pinellas on the recipient's behalf unless a newer human event explicitly confirms procurement teaming.**

No confidential profile bytes, consultant details, or private attachment content belong in this directory.

## Public opportunity boundary

Public Pinellas/OpenGov sources identify the opportunity as **Artificial Intelligence (AI) Strategic Roadmap and Governance Framework Consultant**, project `26-0732-REQ`, with a public due time of **September 15, 2026 at 3:00 PM ET**.

Public routing sources:
- https://procurement.opengov.com/portal/pinellasfl/projects/287743
- https://pinellas.gov/purchasing/
- https://pinellas.gov/purchasing-division-contact-information/

Pinellas' public purchasing material routes formal responses through OpenGov. This carrier does not have buyer submission authority and does not pretend the public summary is the complete controlling packet.

## Proposed paid workshare

Internal commercial hypothesis, **not sent and not binding**: **$15,000 fixed**, subject to owner approval and a real prime/team confirmation.

| Milestone | Share | Proposed amount |
| --- | ---: | ---: |
| Written authorization + kickoff | 40% | $6,000 |
| Draft specialist package | 40% | $6,000 |
| Accepted final specialist package | 20% | $3,000 |

### TJLabs specialist deliverables

1. **AI policy / procurement requirement-to-control matrix** — translate prime-approved policy and procurement requirements into testable control statements, evidence expectations, failure states, and acceptance criteria.
2. **Vendor-risk evidence rubric** — score what a vendor claims versus what can be demonstrated for logging, data handling, authorization, change control, model/tool updates, incident reconstruction, retention, and revalidation.
3. **Design-vs-runtime verification plan** — separate paper controls from runtime behavior, with human-oversight gates, authorization boundaries, provenance, tool/action attribution, and explicit exception handling.
4. **Audit / incident evidence package** — define minimum evidence for reconstructing who/what/when/why around model/tool actions without inventing buyer data or accessing production systems.
5. **Proposal integration + consistency review** — map the agreed specialist artifacts into the prime's response and identify contradictions, unsupported claims, unowned requirements, and revalidation obligations.

### Prime responsibilities stay with the prime

County relationship and buyer communications; OpenGov registration/submission; prime qualifications, references, insurance and legal/financial representations; final strategy and professional judgment; staffing/payroll/subcontract administration; signatures; price presented to the County; and every binding commitment.

## State machine

`validate_readiness.py` intentionally has only three outputs:

- `HOLD_AWAITING_TEAMING_CONFIRMATION` — default and current state.
- `READY_FOR_PRIME_TEAMING_REVIEW` — only after a **new human procurement-teaming confirmation** plus evidence-bound public/current-deadline, controlling-requirement and owner-commercial gates. This is still not send/submission authority.
- `CLOSED_NO_FIT` — when a human closeout proves the provider is staffing-only or otherwise not a fit.

Even `READY_FOR_PRIME_TEAMING_REVIEW` keeps `email_send_authorized=false`, `county_submission_authorized=false`, and the outbound DNR fence intact. A separate exact-target send lease/custody decision is still required before any external mutation.

Run:

```bash
python revenue/pinellas_26_0732_teaming/validate_readiness.py \
  revenue/pinellas_26_0732_teaming/opportunity.json \
  revenue/pinellas_26_0732_teaming/state.json \
  revenue/pinellas_26_0732_teaming/workshare.json

python -m unittest -v revenue.pinellas_26_0732_teaming.tests.test_validate_readiness
python -O -m unittest -v revenue.pinellas_26_0732_teaming.tests.test_validate_readiness
```

The default validator exit is non-zero/HOLD by design.

## Authority ceiling

This carrier can prepare internal paid-workshare artifacts and test their state transitions. It cannot send mail, contact the consultant, contact Pinellas, submit through OpenGov, represent recruiter authority, use confidential profile contents, accept a contract, commit staffing/spend, assert an award/payment, or recognize revenue.
