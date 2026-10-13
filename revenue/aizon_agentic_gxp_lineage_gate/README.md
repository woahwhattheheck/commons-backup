# Agentic GxP lineage evidence gate

This package is a **buyer-neutral, synthetic, evidence-only** delivery primitive for the commercial seam behind `aizon-agentic-gxp-lineage-proof-gate-01`. It does not connect to Aizon, a manufacturing system, a model provider, a batch record, or a quality system.

The gate binds one synthetic artifact to four exact evidence records: a source snapshot, an approved change-control envelope, an execution record, and an explicit human approval. The execution is bound to source/batch hashes, model version, tool versions, prompt-policy version, query/result hashes, actor/role, intended-use risk, and change-control identity. Human approval signs the resulting content digest by reference; it does not grant operational authority.

## Fail-closed controls

- canonical bounded JSON and canonical identifiers/hashes;
- exact-event retries collapse, while same-ID/different-payload events HOLD;
- one artifact and exactly one event of each required kind;
- source/change/execution/approval reference integrity;
- model/tool/prompt/risk scope must match approved change control;
- execution and approver roles must match policy;
- caller-supplied **trusted evaluation time lives outside the evidence payload**;
- policy, source, execution, change control, and approval all expire;
- future-dated evidence beyond bounded skew HOLDs;
- receipts are SHA-256 content-addressed and the verifier re-evaluates the bound evidence instead of trusting a rehashed receipt;
- consumption rechecks current expiry and READY status;
- authority is hard-coded `EVIDENCE_ONLY_NO_GXP_RELEASE`.

## Validation

```bash
python -m unittest revenue.aizon_agentic_gxp_lineage_gate.test_gate -v
python -O -m unittest revenue.aizon_agentic_gxp_lineage_gate.test_gate -v
python -m revenue.aizon_agentic_gxp_lineage_gate.acceptance
```

The deterministic acceptance fixture evaluates 100 synthetic artifacts: 80 clean READY cases and 20 deliberate HOLD cases split across undeclared model versions, approval-digest tampering, conflicting same-ID evidence, and out-of-policy intended-use risk. It also proves order-invariant replay and offline receipt verification.

## Boundary

This module makes **no** GAMP 5, GMP, FDA, validation, quality-release, or regulatory-compliance certification. It never approves or releases a manufacturing batch, deploys a model, calls a provider, processes buyer data, or substitutes for a quality person/reviewer. It is pre-integration evidence and acceptance infrastructure only.

## Live cash

Verified product pages only — no invented Stripe links.
- [$199 dealer diagnostic](../../dealer-service-lead-rescue.html)
- [$199 referral diagnostic](../../referral-intake-completeness.html)
- [$199 repair diagnostic](../../repair-booking-preflight.html)
- [$199 plant diagnostic](../../plant-downtime-handoff.html)
