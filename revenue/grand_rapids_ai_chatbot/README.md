# Grand Rapids 920-45-269 — AI chatbot proposal carrier

Original operation: `GRANDRAPIDS-920-45-269-AI-CHATBOT-ZSOLSTICE-20260913`  
Post-merge authority repair: `GRANDRAPIDS-PREFLIGHT-INDEPENDENT-AUTHORITY-ZLFW3H7-20260913`  
Host-root separation repair: `GRANDRAPIDS-PREFLIGHT-HOST-ROOT-SEPARATION-ZVAK6N8-20260913`  
GitHub issues: `#13870`, `#13884`, `#13918`, `#13972`

This directory is a fail-closed production carrier for the City of Grand Rapids RFP 920-45-269 opportunity. It deliberately separates public/official-source context, proposal-state claims, and **independently authenticated retained authority**.

## What is here

- `requirements.json` — claim/source ledger with `CONFIRMED_OFFICIAL`, `CORROBORATED`, `PACKET_REQUIRED`, and `OWNER_REQUIRED` states.
- `submission_state.json` — untrusted current readiness claims. It remains HOLD and does not pretend the packet, certifications, references, pricing form, registrations, or owner release exist.
- `trusted_authority.py` — strict authority-envelope verifier. It never acquires a trust root itself; trusted host code must inject an independently authenticated generation+digest explicitly.
- `preflight.py` — deterministic fail-closed readiness receipt. The public CLI is deliberately unprivileged and never loads authority bytes or root material, so it cannot produce READY.
- `TRUSTED_AUTHORITY.md` — trust boundary, envelope schema, trusted-host integration, rotation, and operator procedure.
- `acceptance.py` — executable UAT invariant checker for grounding, routing, source freshness/conflict, high-risk holds, duplicate/retry semantics, timeout reconciliation, and replay.
- `proposal_scaffold.md` — technical/administrative proposal carrier with packet insertion points.
- `questions.md` — packet-first clarification ledger and do-not-duplicate access inquiry record.
- `test_preflight.py`, `test_acceptance.py` — hostile regressions.

## Current commercial truth

The controlling RFP/addenda are not held by this lane. Official City Purchasing says MITN is its online procurement/current-opportunity system and current opportunities require vendor login; it also says vendors must register in Vendor Self Service to be paid and publishes EBO policies/forms. Those facts do **not** prove the opportunity-specific forms, evaluation rules, eligibility, certifications, or pricing schedule.

A single access-only email was sent to the named buyer on 2026-09-13 after a provider-level Gmail dedupe returned zero prior Grand Rapids/solicitation/buyer traffic. That email asked only for the authoritative packet/access path and permitted question channel. No reply is claimed.

The landed v1 preflight previously treated non-placeholder strings inside `submission_state.json` as sufficient PASS evidence. v2 removed that state-local authority, but a later implementation still let the public CLI authenticate an authority document against generation/digest values inherited from the same caller-controlled process environment. A caller could therefore fabricate an internally consistent authority, set matching environment values, and collapse the supposed host boundary.

The current design removes ambient trust acquisition entirely. The package does not read a root from environment or CLI. Trusted host integration may call the library only after it has independently authenticated the current authority root. The public CLI never enters that path.

## Verify current state

```bash
python -m unittest discover -s revenue/grand_rapids_ai_chatbot -p 'test_*.py' -v
python -O -m unittest discover -s revenue/grand_rapids_ai_chatbot -p 'test_*.py' -v
python revenue/grand_rapids_ai_chatbot/preflight.py revenue/grand_rapids_ai_chatbot/submission_state.json
```

Expected current public-CLI status: `HOLD`.

The public CLI has **no `--authority` option**. Legacy environment names such as `GRAND_RAPIDS_PREFLIGHT_AUTHORITY_GENERATION` and `GRAND_RAPIDS_PREFLIGHT_AUTHORITY_SHA256` have no authority effect in this package.

A future authenticated evaluation must happen through trusted host integration that supplies an independently authenticated generation+authority digest explicitly to `trusted_authority.load_current_authority(...)`, then passes the resulting `VerifiedAuthority` to `preflight.evaluate(...)`. See `TRUSTED_AUTHORITY.md`.

`READY` is therefore a trusted-host library state, not a portable claim created by proposal bytes or shell environment. It never contacts the buyer, signs, submits, spends, awards, invoices, recognizes revenue, or moves money.
