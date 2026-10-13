# 911 software acceptance harness — offline/synthetic specification

## Purpose and safety boundary

This harness is for **authorized acceptance testing**, preferably in an isolated vendor/buyer test environment with synthetic or properly de-identified fixtures. It is not an operational playbook for live 9-1-1 systems and must not be used to interfere with calls, CAD, radio, dispatch, telephony, evidence, or emergency records.

Human public-safety personnel retain operational authority. The harness evaluates a software product's behavior and evidence trail; it does not make emergency decisions.

## Evidence model

Each fixture should identify:

```text
case_id
workflow_id
fixture_version
source_type
synthetic_or_deidentified
source_digest
policy_or_rubric_version
expected_disposition
allowed_outputs[]
prohibited_outputs[]
required_human_review
expected_side_effect_count
latency_budget_if_applicable
metric_tags[]
```

Each test run should emit a durable receipt containing:

```text
run_id
case_id
started_at
completed_at
product_version
model_or_engine_id_if_exposed
config_digest
rubric_or_policy_digest
integration_contract_digest
input_digest
output_digest
disposition
human_review_receipt_if_required
side_effect_receipts[]
stop_or_escalation_reason
error_class
rollback_or_reset_receipt
metric_observations[]
```

Restricted payloads are referenced by opaque authorized identifiers/digests rather than copied into public artifacts.

## Core test families

### 1. Known-answer normal cases

Use independently reviewed fixtures with expected QA/training/hiring/operations outcomes. A generated score or text response is not sufficient: classification, evidence, human-routing, side effects and audit record must match the agreed contract.

### 2. Missing / malformed information

Omit required fields, corrupt timestamps/identifiers, provide unsupported formats, or remove required evidence. Expected behavior: explicit reject/hold/escalate; no silent fabrication and no unapproved side effect.

### 3. Stale / out-of-window information

Provide data outside the agreed freshness window. Expected behavior: mark stale, request refresh, or escalate per contract. Stale content must not silently become current truth.

### 4. Contradictory inputs

Present mutually inconsistent metadata, transcript cues, QA labels, policy versions, or source-system states. Expected behavior: preserve contradiction, identify the governing source if contractually known, otherwise escalate for human resolution.

### 5. Duplicate / replay / ambiguous retry

Replay the same logical event and simulate a retry after an uncertain response. Expected behavior: no duplicate external side effect; receipt shows idempotency/deduplication disposition.

### 6. Partial input / partial integration failure

Simulate an unavailable dependency or incomplete evidence reference. Expected behavior: visible degraded/blocked state, no silent omission from metrics, and named recovery/escalation owner.

### 7. Permission / role boundary

Attempt a function from a role that should not have it. Expected behavior: denial and attributable audit evidence; no credential substitution, privilege bypass, or fallback to a more privileged identity.

### 8. Human-review boundary

For every agreed human-gated outcome, test approval, denial and no-response. Expected behavior: no gated effect without attributable prior approval; denial/no-response ends in safe hold/escalation.

### 9. QA scoring / rubric drift

Replay the same frozen fixture across an approved rubric/policy/config version change. Expected behavior: differences are surfaced and attributed; old acceptance evidence is not silently reused under the new rubric.

### 10. Training / simulation integrity

For products that generate or score simulation/training cases, verify that scenario version, expected learning objective, scoring rubric, learner attempt and evaluator outcome remain attributable. Synthetic scenarios must not be confused with real incident records.

### 11. Transcript / recording-reference integrity

Where authorized test data includes transcript or recording references, verify:
- source identity and time alignment remain intact;
- truncation/segment loss is detectable;
- speaker/channel mapping uncertainty is visible;
- derived text/labels never overwrite the source record;
- QA conclusions identify the exact evidence version used.

This harness does not instruct anyone to alter or intercept live recordings.

### 12. Case denominator integrity

Inject cases the product cannot process. Expected behavior: failed/unprocessed cases remain visible in denominators and dashboards. A tool must not inflate apparent QA coverage or accuracy by silently excluding hard cases.

### 13. Latency / queue behavior

In an approved test environment, vary non-live synthetic workload and record processing/queue behavior. Any latency budget must come from the buyer/vendor contract; this spec invents none. Over-budget behavior must remain observable and must not cause silent record loss.

### 14. Availability / restart / recovery

For approved non-production test components, test documented restart/recovery paths and confirm in-flight work is either recovered or explicitly failed. No test may be run against live emergency operations without formal buyer authorization and change control.

### 15. Rollback / reset

For every reversible test side effect, intentionally force a later test failure and verify the authorized reset path restores the defined test invariant. Irreversible/live side effects are excluded from this generic harness.

## Regression gate

A prior acceptance result is stale until rerun when any acceptance-critical element changes, including:
- product/model/engine version;
- configuration/prompt/rubric;
- workflow/policy definition;
- tool/API schema;
- upstream/downstream integration behavior;
- identity/role mapping;
- data transformation;
- fixture corpus;
- human approval policy.

Each frozen case is classified `PASS`, `EXPECTED_CHANGE`, `REGRESSION`, or `BLOCKED_BY_ENVIRONMENT`. `EXPECTED_CHANGE` requires owner+rationale and is not an automatic pass.

## Minimum pilot-acceptance gate

The harness may support an acceptance recommendation only when:

- all required normal cases meet the contract;
- all required unsafe/invalid/ambiguous cases hold or escalate correctly;
- replay/retry creates zero duplicate side effects;
- no unprocessed case disappears from denominator evidence;
- required human boundaries are enforced;
- provenance/version lineage is complete;
- agreed reset/recovery tests pass;
- remaining exceptions are enumerated, owned and outside the accepted boundary;
- benefit/quality measurements are reproducible from observed evidence.

The harness provides technical acceptance evidence. It does **not** certify CJIS, HIPAA, legal, labor, procurement, NG9-1-1 or other regulatory compliance.