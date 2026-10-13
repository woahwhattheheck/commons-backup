# Controlling-source recovery runbook

The pursuit is not bid-ready until the controlling solicitation package is acquired from the City of Airdrie or the official procurement system and bound by exact bytes.

## Recovery sequence

1. Navigate from a City of Airdrie or official procurement listing to solicitation `AB-2026-06233`. Do not treat a search-engine snippet, CLEATUS, BidsFactory, TechBids, TenderImpulse, or another mirror as controlling authority.
2. Acquire the solicitation package and every currently published attachment/addendum from that official source. Preserve the original bytes.
3. Compute SHA-256 for each file. Assign stable `source_id` values. Record source kind, currentness, scope completeness, exact official locator, and supersession links.
4. Extract the **controlling deadline with timezone** from official bytes. Do not infer Mountain time merely from the buyer's location.
5. Reconcile amendments before extraction. If an addendum supersedes an older requirement, mark the old source non-current and bind requirements only to current authority.
6. Extract every mandatory, evaluated, and informational requirement with exact source ID, source SHA, section/page/locator, and minimal source-faithful text.
7. Build the evidence register. `PROVEN` requires an actual artifact reference plus its SHA-256. Unknown corporate facts stay `UNKNOWN`, `MISSING`, or `OWNER_ATTESTATION_REQUIRED`.
8. Run the trusted-host evaluator. Resolve `INVALID`, `HOLD_DEADLINE_REVERIFY`, `HOLD_REQUIREMENT_EXTRACTION_REQUIRED`, and `HOLD_MANDATORY_GAPS` before any owner decision.
9. If the result reaches `READY_FOR_OWNER_REVIEW`, independently verify the official portal state again immediately before any authorized external action.

## Required extraction topics

Do **not** assume these are requirements; determine them from the controlling package:

- bidder/entity location, registration, tax, or local-presence rules;
- prime, consortium, subcontractor, and key-person rules;
- municipal/public-sector and data-governance experience;
- references and reference-contact format;
- privacy, security, records-management, data-residency, FOIP/access-to-information, or AI-governance terms;
- insurance, indemnity, licensing, workers compensation, background checks, or conflict declarations;
- deliverables, workshops, stakeholder participation, onsite expectations, schedule, acceptance, and knowledge transfer;
- price form, currency, tax treatment, rate caps, expenses, and negotiation mechanics;
- evaluation weights and mandatory pass/fail gates;
- required forms, signatures, certifications, page/file limits, naming, upload mechanics, and late-bid rules;
- question deadline, named official channel, addendum procedure, and proposal close with timezone.

## Stop conditions

Stop and keep the pursuit on HOLD if the official package cannot be acquired, source identity is ambiguous, an amendment cannot be reconciled, a mandatory requirement lacks truthful evidence, or the submission deadline/currentness cannot be independently verified.

No buyer question or contact is sent by this runbook.

## Live cash

Verified product pages only — no invented Stripe links.
- [$199 dealer diagnostic](../../dealer-service-lead-rescue.html)
- [$199 referral diagnostic](../../referral-intake-completeness.html)
- [$199 repair diagnostic](../../repair-booking-preflight.html)
- [$199 plant diagnostic](../../plant-downtime-handoff.html)
