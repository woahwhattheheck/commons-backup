# Paid Pilot Authorization Gate

This package closes the commercial boundary between **interest / a buyer YES** and **permission to begin exact-scope paid work**. It is deliberately buyer-neutral and provider-neutral: it sends nothing, signs nothing, charges/refunds nothing, grants no credentials, and mutates no external system.

The strongest state is `FUNDED_EXECUTION_READY_EVIDENCE_ONLY`. It means only that the supplied evidence shows the exact content-addressed scope has buyer approval, accepted funding evidence, complete declared intake, any required owner approval, and no expiry/mismatch holds. It does **not** establish legal enforceability, bank cash availability, production access, scope expansion, revenue recognition, or a provider mutation.

States:

- `PROPOSAL_READY`: the scope is coherent and unexpired but one or more positive execution prerequisites are still missing.
- `HOLD`: contradictory, negative, stale, expired, mismatched, or undeclared evidence exists.
- `FUNDED_EXECUTION_READY_EVIDENCE_ONLY`: all configured prerequisites bind the exact same scope hash.

Key fail-closed checks include buyer/funding/intake/owner scope-hash mismatch, buyer NO, unaccepted or non-ready funding state, exact amount/currency mismatch, expired funding, expired/stale scope, incomplete evidence capture, missing/undeclared intake, owner rejection, future-dated evidence, unknown fields, and receipt tampering. The verifier re-evaluates the bound policy and snapshot rather than trusting a self-rehashed receipt.

Run from repository root:

```bash
python -m unittest discover -s revenue/pilot_authorization_gate -t . -p 'test*.py' -v
python -O -m unittest discover -s revenue/pilot_authorization_gate -t . -p 'test*.py' -v
python -m py_compile revenue/pilot_authorization_gate/_core.py revenue/pilot_authorization_gate/gate.py revenue/pilot_authorization_gate/test_gate.py revenue/pilot_authorization_gate/test_temporal.py
```
