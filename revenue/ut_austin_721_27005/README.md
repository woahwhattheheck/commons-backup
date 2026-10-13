# UT Austin 721-27005 — pursuit carrier

**Operation:** `UT-AUSTIN-721-27005-PHASE2-QUALIFY-BUILD-ZCHG5S6-20260916`  
**Issue:** #15051  
**State:** internal evidence carrier; `TEAMING_READY`, **not** `PRIME_READY`; no buyer/portal/submission authority.

This directory turns the public solicitation requirements into a fail-closed pursuit packet. It is intentionally stricter than a proposal draft: every prime-qualification gate that is not backed by evidence remains missing or owner-only. `verify.py` recomputes posture from the evidence file and rejects silent deadline changes, missing official source locators, missing required submission surfaces, unsupported VERIFIED claims, or any attempt to turn on buyer/contact/portal/signature/submission/spend authority.

## Current result

Run:

```bash
python revenue/ut_austin_721_27005/verify.py
python -O revenue/ut_austin_721_27005/verify.py
python revenue/ut_austin_721_27005/test_verify.py
python -O revenue/ut_austin_721_27005/test_verify.py
```

Expected posture is `TEAMING_READY`, because the repo/public site can serve as implementation-artifact evidence and this carrier defines a bounded complementary QA/accessibility/implementation-support workshare. Prime readiness remains blocked on actual comparable-project, curated-portfolio, staffing, pricing, financial, security/EIR, terms/addenda, and authorized-signature evidence.

## What this carrier does not do

It does **not** register on Bonfire/Euna, click Intent to Bid, accept terms, sign, submit, contact UT Austin, contact a prospective prime, spend money, invent references, or claim an award/payment/revenue event. Those are separate provider/owner actions.

See:
- `source_manifest.json` — source locators, deadlines, requested artifacts, scope boundaries.
- `requirements.md` — compliance matrix and response architecture.
- `qualification.json` — evidence state and all-false action authority.
- `delivery_plan.md` — bounded technical/UX delivery and acceptance plan.
- `owner_checklist.md` — owner/prime gates and last-mile schedule.
- `verify.py` / `test_verify.py` — deterministic fail-closed proof.
