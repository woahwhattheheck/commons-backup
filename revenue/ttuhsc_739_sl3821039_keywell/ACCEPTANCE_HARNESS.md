# Acceptance harness specification

## Objective

Turn an AI workflow from a demo claim into rerunnable evidence. The harness tests the workflow contract, not model vibes: each case has known inputs, allowed actions, required approvals, expected disposition, and a durable receipt.

## Canonical case schema

Each fixture should carry at least:

```text
case_id
workflow_id
fixture_version
input_refs[]
input_classification
input_freshness
expected_disposition
allowed_actions[]
prohibited_actions[]
required_approvals[]
policy_version
integration_contract_version
expected_side_effect_count
rollback_expected
metric_tags[]
```

Each run should emit:

```text
run_id
case_id
started_at / completed_at
input_digest
policy_digest
model_or_engine_id
prompt_or_config_digest
integration_contract_digest
tool_calls[]
approvals[]
side_effects[]
disposition
stop_reason
rollback_receipt
metric_observations[]
```

Secrets, credentials, raw PHI, FERPA records, and other restricted content are never stored in public fixtures or public receipts.

## Test families

### 1. Known-answer normal path

Prove the expected business disposition for representative valid cases. A result is not a pass merely because text was produced; the emitted disposition, control path, side effects, ownership and evidence must match the workflow contract.

### 2. Missing / malformed input

Remove required fields, corrupt formats, omit provenance, or present an unsupported data class. Expected result: explicit stop/reject with a reason; no side effect.

### 3. Stale input

Use data outside the approved freshness window. Expected result: refresh/escalate/stop according to contract; never silently treat stale data as current.

### 4. Contradictory evidence

Inject mutually inconsistent authoritative fields or sources. Expected result: deterministic conflict handling and human escalation where policy requires it; no unsupported resolution invented by the agent.

### 5. Duplicate / retry

Replay the same logical event, including transport retry after an ambiguous timeout. Expected result: zero duplicate external state changes; receipt shows idempotency key or equivalent deduplication evidence.

### 6. Timeout / partial dependency failure

Fail one API/tool after another step has succeeded. Expected result: explicit partial-state record, compensating action or safe stop, and a named recovery owner.

### 7. Permission denied / least privilege

Remove an entitlement or attempt a prohibited action. Expected result: denial is visible and terminal unless an approved escalation path exists; no credential substitution or privilege bypass.

### 8. Human approval boundary

For every contractually human-gated action, test both approval and denial/absence. Expected result: no gated action before an attributable approval receipt; denial/absence stops safely.

### 9. Tool/schema drift

Change a tool name, required field, enum, response shape, or policy version. Expected result: fail closed or surface an explicit incompatible-version state before relying on old acceptance evidence.

### 10. Rollback / reset

For agreed reversible side effects, intentionally fail after the side effect and prove recovery. Expected result: final state matches the defined rollback/reset invariant and the receipt identifies what was undone and what remains manual.

## Regression policy

A frozen acceptance set is versioned by content digest. A change to any of the following invalidates the previous acceptance result until rerun: model/engine, prompt/config, system policy, workflow contract, relevant business rule, tool schema, integration endpoint behavior, approval policy, data transformation, or fixture corpus.

The regression report should classify every case as `PASS`, `EXPECTED_CHANGE`, `REGRESSION`, or `BLOCKED_BY_ENVIRONMENT`. `EXPECTED_CHANGE` still requires an owner and rationale; it is not an automatic pass.

## Pilot-ready gate

The harness can support a `pilot-ready` recommendation only when:

- all required normal-path cases pass;
- all required unsafe/invalid cases stop correctly;
- duplicate/retry cases have zero duplicate side effects;
- all required human boundaries are enforced;
- version lineage is complete;
- agreed rollback/reset cases pass;
- every remaining exception has an explicit owner and is outside the approved pilot boundary;
- KPI observations are reproducible from evidence.

The harness cannot certify legal/regulatory compliance by itself. It produces technical evidence for the prime, TTUHSC owners, privacy/security staff, and other authorized reviewers.