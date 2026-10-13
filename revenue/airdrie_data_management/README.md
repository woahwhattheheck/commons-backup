# City of Airdrie AB-2026-06233 — Data Management Consultant

This directory is a **qualification and source-custody carrier**, not a proposal and not a submission tool.

## Current state

`public_notice.json` records a live pursuit discovered in public procurement indexes. Running:

```bash
python qualification.py public_notice.json
```

must return `HOLD_CONTROLLING_PACK_REQUIRED`. That HOLD is deliberate. Discovery mirrors can establish that an opportunity appears to exist; they cannot establish the City's controlling requirements, addenda, submission instructions, or bidder obligations.

The public discovery records currently report:

- City of Airdrie, Alberta;
- solicitation `AB-2026-06233`;
- title `Data Management Consultant`;
- an October 6, 2026 8:00 PM response deadline (timezone not established by the discovery carrier);
- a public-scope summary covering enterprise data ownership, stewardship, standardized business definitions, and responsible/compliant use of data and AI.

Those facts remain **discovery evidence only** until exact City / official-procurement bytes are recovered.

## Authority model

The production CLI accepts only the pursuit packet. It has no argument for trusted procurement sources or authority capabilities and cannot promote itself past the controlling-pack HOLD.

`evaluate_with_trusted_sources()` is a trusted-host integration boundary. Source dictionaries are **claims, not authority**. Promotion additionally requires an `airdrie-controlling-source-authority/v1` document whose HMAC covers the exact canonical source generation: solicitation ID, source IDs and SHA-256 values, City/official-portal authority claim, currentness, scope-completeness, kind, canonical UTC deadline, and supersession set. The authenticated authority generation is then bound into every trusted-path HOLD/READY receipt by schema, key ID, issuance time, and SHA-256.

The HMAC capability is loaded only from the trusted host process variable `AIRDRIE_CONTROLLING_AUTHORITY_KEY_HEX`. It must be at least 32 bytes encoded as canonical lowercase hex. It is **not** accepted from the packet, trusted-source list, authority document, function arguments, or CLI. Code/process access able to read that capability is therefore part of the trusted-host boundary and must not be exposed to untrusted request code. If the capability is absent, malformed, wrong, or the authority document does not exactly match the supplied source generation, the trusted path returns `INVALID` and can never reach `READY_FOR_OWNER_REVIEW`.

A trusted host that has independently reacquired the controlling City / official-procurement bytes can call `issue_host_authority_set()` inside that protected process to bind the exact source generation before requirement extraction. Reissuing authority is required whenever source SHA, deadline, currentness, scope, kind, or supersession changes. Requirements must bind back to one exact current trusted-source ID + SHA and evidence IDs.

Even after host authority verifies and all mandatory evidence is proven, the maximum state is `READY_FOR_OWNER_REVIEW`; `submission_authorized` remains false.

## Status ladder

- `INVALID` — malformed, ambiguous, stale/superseded, source-inconsistent, unauthenticated, or authority-generation-inconsistent evidence.
- `HOLD_CONTROLLING_PACK_REQUIRED` — discovery-only state.
- `HOLD_DEADLINE_REVERIFY` — authenticated controlling deadline reached; amendments/currentness must be re-read and a new authority generation issued.
- `HOLD_REQUIREMENT_EXTRACTION_REQUIRED` — authenticated trusted pack exists, but requirements have not been source-bound.
- `HOLD_MANDATORY_GAPS` — at least one source-bound mandatory requirement lacks proven evidence.
- `READY_FOR_OWNER_REVIEW` — source/host-authority/evidence gates pass; **still no submission authority**.

## Explicit non-authority

Nothing in this carrier authorizes buyer contact, procurement registration, certifications, representations about Canadian eligibility/tax/legal status, insurance claims, references, pricing, submission, signature, contract acceptance, award, payment, deployment, or revenue recognition.

See `SOURCE_RECOVERY.md`, `PROPOSAL_ARCHITECTURE.md`, and `TEAMING_BRIEF.md` for the next owner-controlled work.

## Live cash

Verified product pages only — no invented Stripe links.
- [$199 dealer diagnostic](../../dealer-service-lead-rescue.html)
- [$199 referral diagnostic](../../referral-intake-completeness.html)
- [$199 repair diagnostic](../../repair-booking-preflight.html)
- [$199 plant diagnostic](../../plant-downtime-handoff.html)
