# TraceLink agentic exception decision-evidence gate

Provider-free, synthetic/non-production evidence gate for `tracelink-agentic-exception-decision-evidence-gate-01` and the current bounded TraceLink pilot offer.

The package answers one narrow question: **is the evidence packet complete and internally bound strongly enough for an authorized human owner to review a proposed exception action, or must the packet be held?** It never executes the action.

## Evidence bound into each decision

A strict packet joins:

- originating PO and ASN identity plus EPCIS and quality-event evidence IDs;
- authenticated partner identity/trust evidence, with a canonical partner-state digest;
- object/data-snapshot versions, capture time and canonical snapshot digest under fixed `snapshot-freshness-v1` (30-minute) policy;
- rule version and agent-profile version;
- role plus granted/required permission scope;
- cited source IDs and digests;
- canonical recommendation payload/hash and its PO/ASN references;
- canonical final-action payload/hash and its recommendation binding;
- explicit human approval bound to the final-action hash and a canonical approval-record digest.

Malformed envelopes, unknown durable fields, invalid timestamps/digests, duplicate evidence identities, future snapshots, caller attempts to weaken the fixed freshness policy, corrupted partner/snapshot/approval digests and corrupted recommendation hashes fail closed before a readiness decision is emitted. Missing/insufficient business evidence emits a stable `HOLD` reason instead.

## Stable decision reasons

`evaluate(packet)` emits `REVIEW_READY` or `HOLD` with ordered reasons:

- `UNTRUSTED_PARTNER`
- `STALE_SNAPSHOT`
- `PO_ASN_MISMATCH`
- `MISSING_AGENT_PROFILE_VERSION`
- `PERMISSION_OUT_OF_SCOPE`
- `MISSING_HUMAN_APPROVAL`
- `FINAL_ACTION_HASH_MISMATCH`

The decision also carries the canonical packet digest, cited evidence digests, recommendation/final/approval hash bindings, the snapshot age, a content-addressed receipt, and an explicit all-false action-authority map.

`verify_decision(packet, decision, verify_at=...)` independently recomputes the decision, requires an explicit verification time, and rejects packet/decision tamper, time travel, or stale decision receipts.

## Acceptance contract

From repository root:

```bash
python -m revenue.tracelink_agentic_exception_evidence.acceptance
python -m unittest revenue.tracelink_agentic_exception_evidence.test_gate -v
python -O -m unittest revenue.tracelink_agentic_exception_evidence.test_gate -v
```

The deterministic suite evaluates exactly **140 synthetic exception packets**: 112 `REVIEW_READY` and 28 `HOLD`, exactly four for each of the seven named defect classes. Every decision is verified and a full-suite receipt-set digest is emitted. Re-evaluating the same bytes must reproduce the exact ordered receipt list.

## Authority ceiling

Read-only evidence support only. No order, shipment or allocation change; no recall; no DSCSA filing; no quality disposition; no partner message; no production credential/data access; no provider mutation; no deployment; no contract, payment, or recognized-revenue action. Authorized supply-chain and quality owners retain every consequential approval and execution authority.
