# TurnBench submission-conversion pack

This directory converts the already-landed TurnBench evaluator into an owner-reviewable hackathon submission packet without widening external authority.

## Contents
- `PROJECT_NARRATIVE.md` — ready-to-paste project narrative grounded in landed behavior.
- `JUDGE_DEMO.md` — short synthetic-fixture demo script with explicit claim limits.
- `claim_map.json` — machine-readable separation of source/demo facts from external facts.
- `readiness.py` — strict deterministic readiness compiler/verifier.
- `current_state.json` / `current_state_receipt.json` — current known state: all external gates pending.
- `tests/test_readiness.py` — hostile normal-mode suite; the retained root bridge also re-runs it under `python -O`.

## Readiness gates
The compiler accepts exactly four evidence classes:
1. lablab registration receipt;
2. public-deployment receipt;
3. completed live AssemblyAI session receipt bound to a TurnBench PASS receipt;
4. retained presentation-assets receipt.

No caller boolean such as `registered=true`, `provider_authenticated=true`, or `submitted=true` is admitted. Wrong project/event/source generations fail closed. Live/deployment/presentation evidence older than seven days is stale; registration evidence has a 31-day window. A complete fresh packet reaches only `READY_FOR_OWNER_SUBMISSION_ACTION`.

The compiler does not authenticate providers. Its truth boundary is explicitly `OWNER_RETAINED_EXTERNAL_RECEIPTS_NOT_PROVIDER_AUTHENTICATED_BY_THIS_COMPILER`; a future live provider adapter may strengthen that boundary without changing the all-false action-authority ceiling.

## Authority ceiling
No registration/account/provider/deployment/microphone/submission mutation. No judging, prize, payment, or revenue claim. Final submission remains a separate owner action.
