# Partner Opportunity Qualification Gate

Issue: #15596  
Operation: `PARTNER-OPPORTUNITY-QUALIFICATION-GATE-ZFO1404-20260917`

This package composes after `revenue/procurement_runway_gate`. The upstream gate answers whether the opportunity has usable runway and candidate capacity. This package answers a narrower question: whether a **specific selected candidate** has enough source-bound qualification evidence to be eligible for a separate Muse single-writer election without pretending that unknown eligibility facts are satisfied.

A timing-ready opportunity is not automatically qualification-ready.

## Bounded states

Per partner the compiler emits exactly one bounded state:

- `READY_FOR_MUSE_ELECTION_ONLY` — opportunity runway is admissible, this exact candidate has upstream `EXPLICIT_FIT` or `EXPLICIT_NO_KNOWN_CONFLICT`, contact policy admits a separate Muse election, registration is bounded, every `PRE_OUTREACH` hard gate is satisfied by current exact evidence bound to that gate and partner, and a paid TJLabs workshare exists.
- `READY_FOR_CAPACITY_MUSE_ELECTION_ONLY` — qualification conditions are otherwise bounded, but this exact candidate has upstream `UNKNOWN_CAPACITY`. It authorizes no message; it identifies only a possible separately elected capacity question.
- `HOLD_RUNWAY` — upstream does not select the candidate, opportunity runway is not admissible, or this candidate has `EXPLICIT_MISS`/unsupported timing.
- `HOLD_CONTACT_POLICY` — upstream DNR/inbound-only/unknown/collision policy dominates.
- `HOLD_SOURCE` — solicitation-control evidence is not current.
- `HOLD_REGISTRATION` — registration/screening is unknown, closed, expired, or supported by stale evidence.
- `HOLD_HARD_GATE` — a pre-outreach gate is unsatisfied, unknown, or backed by stale evidence.
- `HOLD_NO_PAID_SEAM` — qualification is otherwise bounded but no paid TJLabs specialist workshare is defined.

Unknown is never upgraded to satisfied.

## Exact source and requirement binding

Every retained source carries:

- `source_id`
- role: `SOLICITATION_CONTROL`, `PARTNER_EVIDENCE`, `REGISTRATION_EVIDENCE`, or `OWNER_WORKSHARE_EVIDENCE`
- `CURRENT | STALE | UNKNOWN`
- exact HTTP(S) URL
- exact SHA-256 of retained bytes
- `observed_on`
- `subject_partner`

Partner/registration evidence must name exactly one packet partner. Control/workshare sources must keep `subject_partner: null`. These are retained operator classifications for deterministic routing; they are **not** external certifications that evidence is true or legally sufficient.

Every source reference carries both source ID and SHA-256. Reusing a source ID after bytes change therefore creates a new semantic generation. The same retained URL or bytes cannot be relabeled across evidence kind or partner subject.

Each hard gate declares:

- `gate_id`
- `phase`: `PRE_OUTREACH | PRE_SUBMISSION | PRE_AWARD`
- human-readable requirement/label
- `required_evidence_kind`: exactly `PARTNER_EVIDENCE` or `REGISTRATION_EVIDENCE`
- `source_refs`

`source_refs` have two jobs. They bind at least one controlling `SOLICITATION_CONTROL` source, and they explicitly bind the exact retained direct-evidence identities admitted for that requirement. A decided disposition (`SATISFIED` or `UNSATISFIED`) must cite current exact-digest evidence of that gate's required kind, bound to that partner, **and that evidence identity must also occur in that exact gate's `source_refs`**.

That last fence prevents same-kind cross-gate evidence transplant. For example, a SAM source bound to `active-sam` cannot satisfy a `three-refs` gate merely because both gates use `PARTNER_EVIDENCE`. If one retained source genuinely supports more than one gate, the packet must explicitly bind that exact identity in each relevant gate; there is no silent reuse.

Hard-gate definitions must bind a solicitation-control source whose URL also appears in the exact upstream runway opportunity's `source_urls`, preventing a gate packet from being transplanted to another solicitation.

## Registration

Registration deliberately separates:

- `requirement_refs`: controlling solicitation evidence that states the registration/screening requirement;
- `evidence_refs`: partner-specific evidence that the registration requirement is complete.

`registration.state = COMPLETE` requires exact `REGISTRATION_EVIDENCE` bound to the evaluated partner. An RFP, generic partner evidence, owner workshare evidence, or another partner's registration source cannot mint completion.

## Phase semantics

Only unresolved `PRE_OUTREACH` gates block a partner approach. Unresolved `PRE_SUBMISSION` and `PRE_AWARD` gates are preserved as later-stage holds. A `READY_*` state is **not** submission readiness, award eligibility, or legal certification.

The phase, requirement text, evidence kind, source association, source currentness, and partner subject are retained operator assertions. The compiler does not read legal text, fetch websites, or determine real-world eligibility itself.

## Upstream runway generation binding

The input embeds exactly one ordinary `procurement-runway-gate-input/v1` packet. This compiler:

1. normalizes that exact upstream input;
2. compiles the canonical upstream runway gate;
3. creates and semantically verifies the upstream receipt;
4. binds SHA-256 for the **normalized upstream input**, upstream output, and upstream receipt into its own output/receipt;
5. uses each selected candidate's own upstream `timing_status`, not merely the opportunity-wide runway state.

This closes two replay/cross-layer predecessors: a semantic upstream input remint cannot replay an older qualification generation merely because upstream output stayed equal, and Partner A cannot make the opportunity globally `READY` while a selected Partner B with `EXPLICIT_MISS` is incorrectly admitted.

## Authority ceiling

Every partner row, top-level output, and receipt hard-carries false authority for:

- partner/buyer contact
- Muse election result
- account registration
- eligibility certification
- portal submission
- signature/contract/award
- payment/cash/revenue recognition

`READY_FOR_MUSE_ELECTION_ONLY` still requires a fresh collision census plus an exact Muse single-writer election before any message. This package does not contact anybody, log into portals, register accounts, submit bids, sign, contract, authorize payment, or recognize revenue.

## Synthetic fixture

`synthetic_input.json` is fictional. It demonstrates one source-bound solicitation, exact upstream composition, an `active-sam` `PRE_OUTREACH` gate whose direct SAM evidence is explicitly included in that gate's `source_refs`, a later unknown `three-refs` gate that does **not** bind the SAM source, registration requirement-vs-completion separation, a bounded `$5,000` owner-authored workshare, and the hard-false authority ceiling.

Do not treat the synthetic URLs or values as a live lead.

## CLI

```bash
out="$(mktemp -d)/qualification"
python -m revenue.partner_opportunity_qualification_gate compile \
  revenue/partner_opportunity_qualification_gate/synthetic_input.json \
  --output-dir "$out"
python -m revenue.partner_opportunity_qualification_gate verify \
  revenue/partner_opportunity_qualification_gate/synthetic_input.json \
  --output-dir "$out"
```

`compile` writes canonical `qualification.json` and `receipt.json`. `verify` independently recompiles both the qualification gate and upstream runway gate and rejects drift.

## Validation

```bash
python -m py_compile revenue/partner_opportunity_qualification_gate/*.py
python -m unittest -v revenue.partner_opportunity_qualification_gate.test_gate
python -O -m unittest -v revenue.partner_opportunity_qualification_gate.test_gate
python -m unittest -v test_partner_opportunity_qualification_gate.py
```

The hostile suite covers requirement-text-as-proof, wrong evidence kind, same-kind cross-gate direct-evidence transplant, cross-partner evidence transplant, registration requirement-vs-completion separation, source digest remint, source transplant/retyping/rebinding, stale/future evidence, upstream-input generation remint with equal upstream output, selected-candidate `EXPLICIT_MISS`, mixed-ready `UNKNOWN_CAPACITY`, DNR dominance, registration expiry/unknown state, missing paid seam, missing/duplicate gates, strict integer typing, duplicate JSON keys, order invariance, and deterministic receipt replay.
