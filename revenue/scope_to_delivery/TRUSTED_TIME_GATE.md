# Scope-to-delivery trusted-time gate

`host/scope_to_delivery.py` remains the canonical content composer for agreements, work packets, execution evidence, delivery receipts, invoice state, and money state. The temporal gate adds exact-byte chronology and current-time prerequisites without granting buyer contact, delivery, payment, provider, cash, or recognized-revenue authority.

## Current authority contract

There are three deliberately different surfaces.

### 1. Parsed-object chronology: `evaluate(...)`

Parsed Python objects have no raw-byte custody. `evaluate(..., as_of=...)` is chronology/audit analysis only. It always emits:

- `clock_authority=CALLER_SUPPLIED_HISTORICAL_ONLY`;
- `raw_byte_provenance_verified=false`;
- `canonical_scope_validated=false`;
- `canonical_project_bound=false`;
- `current_work_authorized=false`.

### 2. Historical exact-byte analysis: `evaluate_bytes(...)`

This surface strict-parses and hashes the exact agreement/observation bytes, re-runs the canonical scope composer on those same bytes, and can bind the exact canonical project. It still accepts caller-supplied `as_of`, so that time is **not current authority**.

Even when chronology is inside the historical window, the output is `HOLD_CALLER_TIME_UNVERIFIED` and `current_work_authorized=false`. Expired historical windows are reported as `HISTORICAL_WINDOW_EXPIRED`. This surface exists for deterministic replay and audit, not for beginning work now.

### 3. Current exact-byte authority: `evaluate_current_bytes(...)`

This is the only receipt compiler that can emit `current_work_authorized=true`. It accepts **no clock argument**. At module construction it closure-binds the original process-UTC clock plus the reviewed exact-byte/canonical compiler helpers, then samples that bound clock when called. Ordinary later rebinding of module `datetime`, helper names, or the public evaluator name therefore cannot redirect the supported current path or the downstream verifier.

This is an application/API input-authority boundary, not a Python sandbox against arbitrary same-process reflection or arbitrary code execution.

A current positive requires all of the following at one closure-bound process observation:

- exact regular-file/byte custody at the caller boundary;
- canonical agreement validation on those exact parsed bytes;
- canonical project binding to those same agreement/observation bytes;
- `written_acceptance.status=PRESENT` with real accepted time;
- acceptance no later than the contracted window end or verifier process UTC;
- verifier process UTC inside the contracted work window;
- every observation bound to the same agreement, at/after acceptance, inside the work window, and no later than verifier process UTC;
- duplicate keys, non-finite JSON, malformed timestamps, oversized/non-byte inputs, symlinked files, project substitution, source substitution, and future evidence fail closed.

A positive receipt states `clock_authority=VERIFIER_PROCESS_UTC_CLOSURE_BOUND`, `provenance_mode=EXACT_RAW_BYTES_VERIFIED`, `canonical_scope_validated=true`, `canonical_project_bound=true`, and `current_work_authorized=true`.

## Downstream verification

### Integrity-only project binding

`verify_project_binding_integrity(project, receipt)` checks receipt self-integrity plus canonical-project digest binding. The compatibility name `verify_project_binding(project, receipt)` delegates to the same integrity-only check.

These functions intentionally return `integrity_valid`, **not generic `valid`**, and always state `current_work_authority_verified=false`. A self-consistent or even caller-fabricated receipt object can at most prove object/digest integrity; it cannot prove that the temporal state is current.

### Authoritative current-work verification

`verify_current_work_authority(agreement_raw, observations_raw, canonical_project=...)` is the production downstream gate. It accepts **no receipt object and no clock argument**. At import time it closure-binds the exact reviewed current evaluator. It reconsumes the exact source bytes, uses the evaluator's closure-bound process UTC, reruns canonical composition/project binding, and returns `valid=true` only when the newly recomputed receipt is exactly `TEMPORAL_PREREQUISITE_READY` with exact provenance and current-work authority.

Therefore a genuine expired/HOLD receipt, a parsed-object receipt, a stale historical receipt, a fabricated/resealed receipt, or later replacement of the public evaluator name cannot be promoted by downstream verification.

## Why the split is required

Earlier generations had distinct false-authority mechanisms:

1. parsed payload A could carry caller-supplied raw SHA claims for unrelated bytes B;
2. a temporal document B could share an agreement ID with canonical document A without being bound to the same canonical artifact;
3. `verify_project_binding(project, receipt)` could return `valid=true` for a genuine expired/HOLD receipt—and could validate a fabricated self-consistent binding object—because it checked project equality but not current temporal authority;
4. an otherwise-correct process-clock wrapper that dynamically looked up mutable module globals could be redirected after import without changing the supported call signature.

The current contract removes authority knobs from parsed helpers, binds canonical composition to the same exact source bytes, makes caller time historical-only, closure-binds the production current path, and requires production verification to recompute from source bytes rather than trust a receipt object.

## Receipt authority ceiling

Every receipt retains:

- `temporal_prerequisite_only=true`;
- `canonical_scope_validation_still_required=true`;
- `external_action_authorized=false`;
- `payment_authorized=false`;
- `delivery_claim_authorized=false`;
- `revenue_authorized=false`.

`current_work_authorized=true` is only a prerequisite for work within an already accepted exact scope. It does not prove buyer identity/permission beyond the canonical agreement, delivery, invoice, settlement, payout, cash, or revenue.

## CLI

The production CLI requires the exact agreement and exact canonical project, plus optional observations:

```text
python3 host/scope_to_delivery_time_gate.py \
  --agreement revenue/scope_to_delivery/fixtures/accepted_agreement.json \
  --observations revenue/scope_to_delivery/fixtures/accepted_observations.json \
  --project /path/to/exact-canonical-project.json
```

There is no `--as-of` override. Exit codes:

- `0`: current prerequisite recomputed READY at closure-bound verifier process UTC;
- `3`: truthful current HOLD, including not-started, expired, non-PRESENT, or unbound project;
- `2`: malformed, unsafe, source-substituted, or canonically inconsistent evidence.

Historical/replay users should call `evaluate_bytes(..., as_of=...)` directly and must treat it as non-current regardless of chronology.
