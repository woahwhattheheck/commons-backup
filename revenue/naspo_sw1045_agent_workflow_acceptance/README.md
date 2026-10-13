# NASPO SW1045 Agent Workflow Acceptance Core

This is a buyer-neutral, offline acceptance core for state-changing AI/agent workflow integrations. It was built to support the bounded specialist seam behind the NASPO SW1045 teaming lane: deterministic approval gates, idempotency/exactly-once evidence, unknown-outcome recovery, tamper-evident receipts, and hostile acceptance testing.

## What it proves

For one declared state-changing action, the core binds the exact principal, resource scope, payload digest, policy version/digest, source snapshot, and human approval into an `action_digest`. Every dispatch must carry the derived idempotency key. The verifier then checks the complete attempt/reconciliation history and refuses to call the trace valid when authority or effect state is ambiguous.

The strongest outputs are:

- `PREFLIGHT_EVIDENCE_READY`: the supplied evidence is internally consistent and current enough for human review, with no dispatch asserted.
- `EXECUTION_EVIDENCE_VALID`: the recorded attempt/reconciliation history is internally consistent and shows at most one provider effect.
- `HOLD`: one or more named invariants failed.

Even the two READY/VALID states set `external_action_authorized=false`. This package does not dispatch actions or convert evidence into execution authority.

## Safety/reliability invariants

- Authority-driving timestamps require explicit UTC `Z`; host-timezone parsing is never used.
- Snapshot freshness and approval expiry use an out-of-band trusted evaluation time.
- Approval binds the exact action, policy, snapshot, principal, and resource scope.
- Idempotency keys bind request + action digest.
- A confirmed provider effect forbids a later dispatch.
- Timeout/unknown outcomes must be reconciled before any retry.
- `UNKNOWN + AMBIGUOUS` remains HOLD; it is never translated into safe retry.
- `UNKNOWN + NOT_FOUND` or `FAILED` may permit a later retry; `UNKNOWN + SUCCEEDED` consumes the effect.
- Multiple distinct provider effects HOLD.
- Strict JSON/plain-object/scalar types reject integer-equivalent floats, duplicate keys, NaN/Infinity, extra fields, and dict subclasses at the public boundary.
- Receipts are canonical JSON SHA-256 commitments and can be recomputed offline.

## Local gate

```bash
cd revenue/naspo_sw1045_agent_workflow_acceptance
python -m py_compile gate.py acceptance.py test_gate.py
python -m unittest -v test_gate.py
python acceptance.py
python -O -m unittest -v test_gate.py
python -O acceptance.py
```

The synthetic acceptance corpus contains 120 workflows: 100 valid execution traces and 20 deliberate HOLDs, five each for stale snapshot, approval-binding mismatch, unresolved unknown outcome, and duplicate provider effect.

## Explicit non-authority

This package does **not** contact NASPO, Oklahoma, Avaap, any buyer, provider, or customer. It does not mutate Workday/Oracle/ERP/HCM systems, create credentials, send messages, submit proposals, sign contracts, initiate/receive payment, certify procurement compliance, assert prime qualification, or recognize revenue. Production identity, access-control, provider APIs, buyer approvals, policy ownership, and final acceptance remain outside this artifact.
