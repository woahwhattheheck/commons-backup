# Ingham County 112-26 — independent 911 technology acceptance workstream

**Operation:** `INGHAM-11226-911-ACCEPTANCE-ZSOL13-20260913`  
**Carrier:** Commons #14262  
**State:** `CONTACT_HOLD`  
**Commercial path:** paid specialist acceptance/evaluation workshare; no price/team/award/payment/revenue claim.

## What this package is

Ingham County has a live solicitation, **112-26 — Advanced Technology Solutions to Enhance 911 Center Operations**, with a mandatory pre-proposal meeting on September 17, questions due September 24, and proposals due October 15, 2026. Public scope summaries describe software intended to improve operations, training quality, QA and hiring outcomes.

This package turns that opportunity into a vendor-neutral, revenue-capable specialist workshare: reproducible acceptance evidence for whichever qualified product/vendor is actually in the procurement. It does **not** pretend TJLabs is a CAD/CHE/telephony prime, does not authorize contact while collision checks are unavailable, and does not touch live emergency operations.

## Why independent acceptance can matter here

Public County records show a heterogeneous environment and operational pain around QA coverage, review time, training, supervisor load and staffing. The risk in adding more automation is not just whether a demo looks good; the buyer needs evidence that difficult cases remain visible, human authority is preserved, retries do not duplicate effects, version/rubric changes invalidate stale evidence, and claimed workforce/quality improvements are measured rather than asserted.

## Files

- `SOURCE_LEDGER.md` — official facts vs secondary scope signals vs historical County context; explicitly records the inaccessible packet/Addendum 1.
- `OPPORTUNITY_AND_WORKSHARE.md` — go/no-go logic and a five-milestone paid acceptance workshare with binary criteria/exclusions.
- `ACCEPTANCE_HARNESS.md` — offline/synthetic test design for QA/training/hiring/operations evidence, hostile conditions, human gates, denominator integrity, recovery and regression.
- `INTEGRATION_AND_MEASUREMENT.md` — vendor-neutral integration evidence contract, public environment map, data/human-authority boundaries and reproducible workforce/quality metrics.
- `PREPROPOSAL_BRIEF.md` — internal high-value questions for the mandatory meeting or an eligible attending partner; does not authorize contact/registration.
- `response_readiness.json` — fail-closed machine state.
- `validate_response_readiness.py` — deterministic validator with hostile self-tests.

## Single-writer / outreach fence

At package creation:

- Commons/SMB issue/PR/code searches found no materially same 112-26 claim;
- Slack could not be searched successfully because the provider returned HTTP 429;
- Gmail could not be searched successfully because the provider returned `rateLimitExceeded`.

Therefore **internal build custody is claimed; external-route custody is not**. `new_external_contact_authorized=false` remains hard-gated until both available coordination surfaces are checked or another durable owner receipt establishes the route.

No one should use this package as permission to email the County, register for the meeting, contact a vendor, submit a proposal, or represent a team relationship.

## Safety boundary

Default work is synthetic/de-identified and non-production. No live 9-1-1 call intervention, autonomous dispatch/resource decision, alteration of emergency records, production credential use, disruptive testing, restricted-data publication, or regulatory certification is part of this generic workshare.

## Next commercial gate

If the controlling packet is recovered and a qualified/eligible vendor confirms interest, the next useful external artifact is a **priced milestone SOW/subcontract** for one or more accepted workflows. Until role, scope, environment, data/security, procurement eligibility and pricing authority are evidenced, status stays `CONTACT_HOLD` / `PROPOSAL_HOLD`.