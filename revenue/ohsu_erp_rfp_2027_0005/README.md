# OHSU ERP RFP 2027-0005 — qualification + paid workshare evidence carrier

## Current source-bound decision surface

The original Zeta-Sol carrier from #14077 and its provider-truth correction #14083 remain intact for provenance. The **current source-bound qualification surface** is `source_bound.py`; it incorporates the exact buyer-source generation received on 2026-09-13/14 without publishing the buyer-distributed workbooks or contract into this public repository.

`source_manifest.json` binds only source hashes, sizes, normalized deadlines, seven normalized minimum gates, the buyer-controlled qualification-composition rule, and normalized contract-review gates. The received files remain outside the public repo:

- controlling RFP workbook SHA-256 `4d4c634ac5f7846dac54692c8d7d2c57a6512f8c2f6984be1c36f2a8dc99f90e`;
- supplier Q&A workbook SHA-256 `40815c4a57d9d82cf07e4db6b2b6f1dfc6512c7fa4cf996af6ec364608722cf0`;
- Professional Services Contract SHA-256 `2716d395072efbe4de6bdcca780f16a2aacbef69e7f542e66c7ca33ce980ed35`.

The buyer-source generation fixes the intent deadline at **2026-09-16 17:00 Pacific** and proposal deadline at **2026-09-25 17:00 Pacific**. The NOI route is a brief email to the issuing contact; that is a source fact, **not send authority**. Every external-action flag remains false.

The supplier Q&A materially changes qualification composition: evidence supplied by a **named and committed** subcontractor/teaming partner may supplement the Respondent while the prime remains responsible. `source_bound.py` therefore assigns every satisfied minimum gate an explicit basis:

- `RESPONDENT` — evidence belongs to the Respondent itself;
- `NAMED_COMMITTED_TEAM_PARTNER` — evidence belongs to the exact partner named in a confirmed teaming commitment;
- `NONE` — the gate is not satisfied.

An unconfirmed outreach target contributes **zero** qualification evidence. A partner row cannot be used outside a `TEAMING` route, cannot survive commitment revocation, and must match the exact committed partner identity. A direct-prime route cannot borrow partner evidence. This prevents research targets or unanswered outreach from silently becoming credentials.

The Professional Services Contract is now a third required source binding rather than an untracked attachment. The packet exposes normalized owner-review gates for work-product/background-tool rights, subcontracting consent, insurance, public-records/confidentiality, termination, conditional HIPAA/network obligations, and the unresolved **payment-terms source conflict**: the RFP workbook states Net 60 while the PSC payment section states Net 30. This carrier does not decide which term governs; it requires owner review before contract acceptance and keeps `contract_accepted=false`.

`current_position.json` deliberately records the live internal posture as `TEAMING` + `UNCONFIRMED` with all seven gates `UNKNOWN`: it is a candidate route, not readiness. `COMMERCIAL_STATUS.md` records the anti-duplicate commercial truth: Huron already received the existing **$12,500 fixed evidence/traceability workshare** offer, there was no reply at the latest inbox census, and the offer remains `PROPOSED_NOT_ACCEPTED` with delivery/milestones `TO_NEGOTIATE`.

### Current source-bound CLI and tests

```bash
python -m revenue.ohsu_erp_rfp_2027_0005.source_bound compile < input.json
python -m revenue.ohsu_erp_rfp_2027_0005.source_bound verify < verify.json

python -m unittest revenue.ohsu_erp_rfp_2027_0005.test_source_bound
python -O -m unittest revenue.ohsu_erp_rfp_2027_0005.test_source_bound
```

The source-bound hostile suite covers wrong buyer-source generations including the PSC, omitted minimum gates, fake qualification inheritance from an unconfirmed target, partner-identity mismatch, direct-prime borrowing, confirmed-team composition, remaining gaps, exact NOI chronology, packet-currentness checks, contract-review integrity, bool/int aliases, and strict-JSON duplicate-key refusal. The scoped workflow also reruns the original carrier suite so the source upgrade cannot silently regress Zeta-Sol's v1 behavior.

## Original public-notice carrier — retained for provenance

The original carrier converts the **public OHSU bid notice** for `RFP-2027-0005` into a deterministic, fail-closed owner-review packet. Its `profile.json` intentionally records the state that existed when that carrier was created: the public notice was not treated as the controlling RFP package and qualifications were not inferred from the notice.

The reviewed public OHSU bids notice identifies **Enterprise Resource Planning (ERP) Assessment and Advisory Services**, issued **2026-08-21**, with intent to bid dated **2026-09-16** and proposal due **2026-09-25**. Its public scope is a comprehensive current ERP landscape assessment, future-state requirements, and an ERP modernization roadmap aligned to institutional goals, operational scale, and regulatory obligations. The notice names Royce Bitter, Senior Sourcing Manager, as contact. Source: `https://www.ohsu.edu/procurement/bids`.

`profile.json` remains an historical input to `qualification.py`; changing the public dates, title, contact, URL, or scope is a contract error instead of a way to widen readiness. New owner decisions should prefer `source_bound.py` because the later source generation is now materialized and hash-bound.

## Commercial hypothesis — not a sale

A bounded **$12,500 fixed paid workshare** is compiled into every packet as `PROPOSED_NOT_ACCEPTED`; delivery timing and milestones remain explicitly `TO_NEGOTIATE`:

- source-bound requirement register across interviews, current-state artifacts, controls, and future-state needs;
- requirement → evidence → owner → gap/risk traceability with orphan detection;
- deterministic coverage and contradiction reports across finance, HR, supply-chain, and administrative workflows;
- decision receipts separating observed current-state evidence, stakeholder assertions, and consultant recommendations;
- AI/automation opportunity entries with explicit human approval, source provenance, and control requirements.

This is designed to sit behind a qualified ERP advisory prime if Token Junkie Labs cannot truthfully prove prime eligibility. It is not OHSU pricing and is not accepted work until an authorized counterparty actually agrees.

## Authority boundary

The strongest state is **owner review only**. No state authorizes buyer/partner contact, intent filing, proposal submission, qualification/reference claims, contracting, payment, award, or revenue recognition. A SHA-256 is a content commitment, not source authentication; callers still have to bind evidence to the correct source and counterparty generation.

The legacy `qualification.py` CLI remains available for historical/public-notice replay:

```bash
python -m revenue.ohsu_erp_rfp_2027_0005.qualification compile < input.json
python -m revenue.ohsu_erp_rfp_2027_0005.qualification verify < verify.json
python -m unittest revenue.ohsu_erp_rfp_2027_0005.test_qualification
python -O -m unittest revenue.ohsu_erp_rfp_2027_0005.test_qualification
```
