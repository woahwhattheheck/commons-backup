# UIOWA-102 — specialist adapter compatibility report

Status: SYNTHETIC INTEGRATION EVIDENCE / NOT A UNIVERSITY FINDING

## Target contract

The adapters target the merged UIOWA-023 evidence register and its structural validator:

- register: revenue/uiowa_rfq_18649_workshare/methodology/23-synthetic-evidence-register.csv
- register blob: fc2ef567e3f9b3f5a5031c74994e62c62b1d9c7e
- validator: revenue/uiowa_rfq_18649_workshare/methodology/validate_23_evidence_register.py
- validator blob: c0a71aa8566c89a1ac3dc8fb2b8e67417801c081

The common register requires 22 fields. UIOWA-102 preserves source-specific information through five explicit extension columns rather than dropping fields.

## Example run 1 — delivery metrics

Input: revenue/uiowa_rfq_18649_delivery_metrics/fixtures/synthetic_deployments.csv

Input Git blob: 8fac02fb9d947deed7df99d563ab05d949127793  
Input SHA-256: fc7469008c5b2eba5d41cae13667d376a6d6acedbddf04dceb16ceee363b482d

Output:
- examples/delivery_to_register.csv
- examples/delivery_to_register.json
- 8 evidence rows
- common-validator invariant check: zero errors

The adapter preserves every deployment native record, original deployment_id, exact source locator, source digest, intervention flag, recovery time, unplanned-rework flag, and notes. A single event remains SINGLE representativeness and is not converted into a population metric or maturity conclusion.

## Example run 2 — security event review

Input: revenue/uiowa_rfq_18649_security_event_review/fixtures/synthetic_events.json

Input Git blob: 3d988e919f9c395eeb08f8171f04cafaea3df143  
Input SHA-256: 2a74bee7d51c064ddaf51e10db3b62986133576c25321ca23705ff045e5d590e

Output:
- examples/security_to_register.csv
- examples/security_to_register.json
- 5 evidence rows
- common-validator invariant check: zero errors

Semantic boundaries survive adaptation:
- monitoring-only ESS-MON-001 remains a monitoring-only signal rather than a security-review finding;
- ESS-SEC-003 has security relevance but missing review evidence, so it becomes NO_EVIDENCE_OBSERVED / NOT_EVIDENCED rather than a fabricated failure;
- RIS-UNK-004 keeps unknown security relevance;
- IAM-SEC-005 retains action.status=in_progress in extensions_json rather than being flattened to closed.

## Example run 3 — AI readiness facts

Input: revenue/uiowa_rfq_18649_synthetic_collection/facts.json

Input Git blob: d715a392b92b4738070552f7cecb8f32a4ddc765  
Input SHA-256: 0b96e53f8f7934cf85c350eaa8162a032910bdc517746dc4b1130aa9ab0237ef

Output:
- examples/ai_to_register.csv
- examples/ai_to_register.json
- 6 AI-readiness evidence rows
- common-validator invariant check: zero errors

This source is explicitly the merged UIOWA-091 AI-readiness fact slice, not a claim that the still-building dedicated AI kits were already merged. Curated strength/gap facts are NEAR_DIRECT / LOW until underlying evidence is reviewed. Unknown facts remain NO_EVIDENCE_OBSERVED / NOT_EVIDENCED.

## Combined run

examples/all_to_register.csv and examples/all_to_register.json contain 19 rows. Provider-readback validation reproduced the UIOWA-023 ID, enum, conflict, absence, required-field, and group/area scope checks with zero errors. Evidence IDs, observation IDs, and finding IDs are deterministic and use non-overlapping synthetic sequence ranges.

## Preservation guarantee

Every output row carries:
- source_component;
- native_id;
- synthetic=true;
- source_sha256; and
- extensions_json containing the complete original native record.

This means a field unsupported by the common 22-column register remains inspectable instead of disappearing.

## Scope limit

These are synthetic integration runs. A structurally valid register row is not proof of a University fact, maturity level, compliance condition, security weakness, delivery performance result, or AI-adoption state.
