# AI workflow lifecycle review

**SYNTHETIC_SUPPLIED_OBSERVATIONS — DRAFT_ANALYSIS_ONLY**

Workflow: fictional-doc-assistant; group: ESS.

## Version timeline

| Version / parent | Changed | Reason | Support owner |
|---|---|---|---|
| v1 / UNKNOWN | 2026-09-01T09:00:00Z | Baseline on four synthetic evidence-handling tasks. | Fictional application-support role |
| v2 / v1 | 2026-09-02T09:00:00Z | Changed both model and prompt; attribution is confounded. | Fictional application-support role |
| v3 / v2 | 2026-09-03T09:00:00Z | Restore explicit uncertainty/freshness instructions; assess repair. | Fictional application-support role |
| v4 / v3 | 2026-09-04T09:00:00Z | Changed evaluation set and lost runtime ownership/retention evidence. | UNKNOWN |

### v1: reproduction evidence

Runs: r1, r1-repeat; replays: baseline-repeat.

| Component | Artifact | Evidence state | Locator |
|---|---|---|---|
| model | model1 | inline_digest_verified | synthetic://fixture/model1 |
| prompt | prompt1 | inline_digest_verified | synthetic://fixture/prompt1 |
| input_snapshot | snapshot | inline_digest_verified | synthetic://fixture/snapshot |
| evaluation_set | eval1 | inline_digest_verified | synthetic://fixture/eval1 |
| rubric | rubric | inline_digest_verified | synthetic://fixture/rubric |
| code | code1 | inline_digest_verified | synthetic://fixture/code1 |
| environment | env1 | inline_digest_verified | synthetic://fixture/env1 |
| configuration | config1 | inline_digest_verified | synthetic://fixture/config1 |

Gaps: none in required metadata; this is not a reproduction guarantee.

### v2: reproduction evidence

Runs: r2; replays: not demonstrated.

| Component | Artifact | Evidence state | Locator |
|---|---|---|---|
| model | model2 | inline_digest_verified | synthetic://fixture/model2 |
| prompt | prompt2 | inline_digest_verified | synthetic://fixture/prompt2 |
| input_snapshot | snapshot | inline_digest_verified | synthetic://fixture/snapshot |
| evaluation_set | eval1 | inline_digest_verified | synthetic://fixture/eval1 |
| rubric | rubric | inline_digest_verified | synthetic://fixture/rubric |
| code | code1 | inline_digest_verified | synthetic://fixture/code1 |
| environment | env1 | inline_digest_verified | synthetic://fixture/env1 |
| configuration | config1 | inline_digest_verified | synthetic://fixture/config1 |

Gaps: none in required metadata; this is not a reproduction guarantee.

### v3: reproduction evidence

Runs: r3, r3-repeat; replays: repair-repeat.

| Component | Artifact | Evidence state | Locator |
|---|---|---|---|
| model | model2 | inline_digest_verified | synthetic://fixture/model2 |
| prompt | prompt3 | inline_digest_verified | synthetic://fixture/prompt3 |
| input_snapshot | snapshot | inline_digest_verified | synthetic://fixture/snapshot |
| evaluation_set | eval1 | inline_digest_verified | synthetic://fixture/eval1 |
| rubric | rubric | inline_digest_verified | synthetic://fixture/rubric |
| code | code1 | inline_digest_verified | synthetic://fixture/code1 |
| environment | env1 | inline_digest_verified | synthetic://fixture/env1 |
| configuration | config1 | inline_digest_verified | synthetic://fixture/config1 |

Gaps: none in required metadata; this is not a reproduction guarantee.

### v4: reproduction evidence

Runs: r4; replays: not demonstrated.

| Component | Artifact | Evidence state | Locator |
|---|---|---|---|
| model | model2 | inline_digest_verified | synthetic://fixture/model2 |
| prompt | prompt3 | inline_digest_verified | synthetic://fixture/prompt3 |
| input_snapshot | snapshot | inline_digest_verified | synthetic://fixture/snapshot |
| evaluation_set | eval2 | inline_digest_verified | synthetic://fixture/eval2 |
| rubric | rubric | inline_digest_verified | synthetic://fixture/rubric |
| code | code1 | inline_digest_verified | synthetic://fixture/code1 |
| environment | env-lost | not_retained | synthetic://fixture/environment-not-retained |
| configuration | config1 | inline_digest_verified | synthetic://fixture/config1 |

Gaps: environment: not_retained; support owner not recorded; model version is not pinned to a recorded immutable revision; random seed not recorded; deterministic replay cannot be assumed.

## Explicit run comparisons

All deltas are candidate minus baseline; subset means exclude missing observations.

### changed-evaluation: incomparable

r3 → r4; changes: evaluation_set, environment, model_revision, model_alias_is_mutable, seed.
No numerical delta: evaluation_set digest missing or changed; case universe changed.
Recorded association only; no causal attribution or production benefit is established.

### regression: descriptive_comparison

r1 → r2; changes: model, prompt, model_revision.

| Metric | Paired / expected | Baseline | Candidate | Delta | Coverage | Better |
|---|---|---|---|---|---|---|
| correctness | 3 / 4 | 1.0 | 0.333333 | -0.666667 | subset_only | higher |
| completeness | 3 / 4 | 1.0 | 0.5 | -0.5 | subset_only | higher |
| usefulness | 3 / 4 | 1.0 | 0.333333 | -0.666667 | subset_only | higher |
| repair_minutes | 3 / 4 | 1.333333 | 7.333333 | 6.0 | subset_only | lower |
| latency_ms | 4 / 4 | 1100.0 | 1200.0 | 100.0 | complete | lower |
Recorded association only; no causal attribution or production benefit is established.

### repair: descriptive_comparison

r2 → r3; changes: prompt.

| Metric | Paired / expected | Baseline | Candidate | Delta | Coverage | Better |
|---|---|---|---|---|---|---|
| correctness | 3 / 4 | 0.333333 | 1.0 | 0.666667 | subset_only | higher |
| completeness | 3 / 4 | 0.5 | 1.0 | 0.5 | subset_only | higher |
| usefulness | 3 / 4 | 0.333333 | 1.0 | 0.666667 | subset_only | higher |
| repair_minutes | 3 / 4 | 7.333333 | 1.666667 | -5.666667 | subset_only | lower |
| latency_ms | 4 / 4 | 1200.0 | 1300.0 | 100.0 | complete | lower |
Recorded association only; no causal attribution or production benefit is established.

## Recorded replay outcomes

- baseline-repeat: exact_on_recorded_cases; 4/4 content-verified cases; differences: none. Finite recorded outputs only; not a guarantee of future provider behavior.
- repair-repeat: different_recorded_outputs; 4/4 content-verified cases; differences: c2. Finite recorded outputs only; not a guarantee of future provider behavior.

## Runtime and investigation trace

| Event | Version / time | Kind | State | Owner | Resolves / resolution | Summary | Evidence / runs |
|---|---|---|---|---|---|---|---|
| incident1 | v2 / 2026-09-02T10:02:00Z | incident | resolution_recorded_with_evidence | Fictional application-support role | UNKNOWN / resolution1 | Synthetic regression: uncertainty mishandled and one timeout. | investigation1, r2 |
| investigate1 | v2 / 2026-09-02T11:00:00Z | investigation | not_an_incident | Fictional evaluator role | UNKNOWN / UNKNOWN | Both model and prompt changed; cannot isolate their effects. | investigation1, r2 |
| resolution1 | v3 / 2026-09-03T11:02:00Z | resolution | not_an_incident | Fictional application-support role | incident1 / UNKNOWN | Recorded repair evidence; exact wording still varies. | repair-check, r3, r3-repeat |
| incident2 | v4 / 2026-09-04T10:02:00Z | incident | open | UNKNOWN | UNKNOWN / UNKNOWN | Environment retention and support ownership need follow-up; no production defect inferred. | r4 |

## Interpretation limits

- No model was called or rescored. Fixture observations are not University findings.
- A verified digest checks local bytes, not truth, authorship, model weights, or production reproducibility.
- Incomplete paired subsets must not be generalized to the full workload.
- This report does not set maturity ratings, approve deployment, procure products, or establish savings.
