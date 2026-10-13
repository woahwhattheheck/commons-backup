# TTUHSC 739-SL3821039 — Keywell response-readiness package

**Operation:** `TTUHSC-739-KEYWELL-WORKSTREAM-ZSOL13-20260913`  
**Carrier:** Commons issue #14249  
**State:** `HOLD_FOR_PARTNER_FACTS`  
**External single-writer:** the pre-existing Keywell Gmail thread; this package authorizes no new contact.

## Purpose

This package prepares the bounded technical subcontractor workstream already promised in the existing Keywell teaming inquiry for Texas Tech University Health Sciences Center RFP 739-SL3821039, **Enterprise AI Adoption & Enablement**.

It is deliberately narrower than the prime contract. TJLabs is not represented here as the prime bidder, healthcare compliance owner, VetHUB owner, holder of three qualifying institutional references, or an already accepted teaming partner. Those facts remain unknown until an eligible prime supplies them.

The commercial posture is explicit: this is a **paid subcontract/work-package path**. The artifacts define a technically useful scope that a qualified prime can incorporate and price. They do not offer indefinite free implementation and they do not create a price, contract, teaming agreement, award, or revenue claim.

## Controlling facts used

The public 41-page RFP states:

- proposal deadline: **September 21, 2026 at 4:30 PM Central Time**;
- written-question deadline: **August 21, 2026**;
- anticipated term: execution through **August 31, 2027**;
- evaluation: **Service Specifications 55% / Pricing 30% / Experience & Reputation 15%**;
- one complete proposal, with an authorized signature; TechBid is preferred;
- a completed **VetHUB Subcontracting Plan** is required; failure to return it is non-responsive;
- TTUHSC may award all or part of the requirement and may award multiple agreements;
- service scope includes strategy/governance, change activation, workforce training, workflow automation/custom AI, agentic governance, adoption/ROI analytics, security/privacy, and knowledge transfer;
- pricing is structured as a not-to-exceed fixed fee for deliverables with level-of-effort detail plus a resource rate card;
- the proposal requests at least three current/recent similar client references and includes bidder/compliance obligations that must remain with the actual prime unless explicitly allocated otherwise.

See `SOURCE_LEDGER.md` for source coordinates and the distinction between controlling RFP text and third-party discovery pages.

## Package

- `KEYWELL_WORKSTREAM.md` — partner-ready bounded workstream.
- `ACCEPTANCE_HARNESS.md` — deterministic evaluation and pilot-verification design.
- `RACI_SECURITY_ROI.md` — prime/subcontract/owner boundaries, data handling, and measurable value instrumentation.
- `SOURCE_LEDGER.md` — controlling-source ledger and discrepancy notes.
- `response_readiness.json` — machine-readable gate state.
- `validate_response_readiness.py` — fail-closed validation, including hostile self-tests.

## Release rule

`response_readiness.json` must remain `HOLD_FOR_PARTNER_FACTS` until the existing sender receives concrete partner evidence. The validator rejects a silent flip to ready while any required partner fact remains unknown.

A positive Keywell reply can unblock drafting of a priced subcontract proposal only after, at minimum, the pursuing-prime status, procurement eligibility, intended TJLabs role, selected workflow(s), security/data boundary, compliance ownership, schedule, and pricing authority are known.

No buyer contact, partner contact, portal submission, signature, certification, pricing commitment, spend, award, payment, or revenue recognition is authorized by these files.