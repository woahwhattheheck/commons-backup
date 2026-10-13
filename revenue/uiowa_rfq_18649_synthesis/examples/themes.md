# Cross-group synthesis

Data status: **synthetic**. Dataset: synthetic-cross-group-028.

Group reach is not corroboration. Correlation clusters are declared, not proven independent; competing explanations and all evidence roles remain visible.

| Theme | Practice | Groups | Relationship | Status | Sources / declared clusters | Action |
|---|---|---|---|---|---|---|
| TH-b3036b7b54de | ai-summary-review | ESS | unresolved_or_inapplicable | unresolved | 1 / 1 | focused_follow_up |
| TH-d75b174ed537 | ai-summary-review | IAM | unresolved_or_inapplicable | unresolved | 0 / 0 | focused_follow_up |
| TH-a7b48ea04a73 | business-recovery-check | ESS, IAM, RIS | inherited_dependency | contested | 1 / 1 | focused_follow_up |
| TH-f0df56ec6431 | delivery-wait | ESS | local_exception | sample_supported | 1 / 1 | group_specific_action |
| TH-5b594f42f08e | delivery-wait | RIS | local_exception | sample_supported | 1 / 1 | group_specific_action |
| TH-f8d5ace9cb2d | release-identity | ESS, IAM, RIS | shared_capability | sample_supported | 1 / 1 | coordinate_shared_owner_and_verify_group_effects |
| TH-9d3e60096f4e | requirements-review | ESS, RIS | repeated_local_practice | sample_supported | 2 / 2 | coordinate_options_keep_group_implementation |
| TH-70141bd4d04f | requirements-review | IAM | unresolved_or_inapplicable | unresolved | 0 / 0 | focused_follow_up |

## TH-b3036b7b54de

Window: 2026-08-01 to 2026-08-31. Scope: sampled_groups_only. Basis: reported_or_mixed.

Groups not covered by this theme: IAM, RIS.
Related findings outside this theme: F-AI-IAM.

Proposed owner role: affected group practice owners.

- **F-AI-ESS / ESS / strength**: Synthetic ai-summary-review strength Context: Policy intent only. Do not call it demonstrated adoption. Supports: AI-POLICY; dissent: none; limitations: none. Mechanism: review-generated-summary (hypothesis); sources: AI-POLICY. 
- Source **AI-POLICY**, policy, version 1, origin AI-POLICY: synthetic://synthesis/AI-POLICY — Worked record AI-POLICY. Fictional policy proposes documenting model inputs and reviewing generated summaries.

Supplied sample and analyst annotations only; no population prevalence, independence, causal proof, maturity, approval or University finding is established.

## TH-d75b174ed537

Window: 2026-08-01 to 2026-08-31. Scope: sampled_groups_only. Basis: reported_or_mixed.

Groups not covered by this theme: ESS, RIS.
Related findings outside this theme: F-AI-ESS.

Proposed owner role: affected group practice owners.

- **F-AI-IAM / IAM / not_applicable**: Synthetic ai-summary-review not_applicable Context: Fictional example, not a University finding. Supports: none; dissent: none; limitations: none. Mechanism: unknown (unknown); sources: none. Fictional scoped service does not generate AI summaries. Revisit if the scope changes.

Supplied sample and analyst annotations only; no population prevalence, independence, causal proof, maturity, approval or University finding is established.

## TH-a7b48ea04a73

Window: 2026-08-01 to 2026-08-31. Scope: sampled_all_three_groups. Basis: observed.

Groups not covered by this theme: none.
Related findings outside this theme: none.

Proposed owner role: shared service owner with affected group leads.

- **F-RESTORE-ESS / ESS / gap**: Synthetic business-recovery-check gap Context: One shared service supplies recovery to three fictional groups; evidence is reused, not replicated. Supports: RECOVERY-EXERCISE; dissent: none; limitations: none. Mechanism: missing-business-check (supported); sources: RECOVERY-EXERCISE. 
- **F-RESTORE-IAM / IAM / gap**: Synthetic business-recovery-check gap Context: One shared service supplies recovery to three fictional groups; evidence is reused, not replicated. Supports: RECOVERY-EXERCISE; dissent: IAM-COUNTEREXAMPLE; limitations: none. Mechanism: missing-business-check (supported); sources: RECOVERY-EXERCISE. 
- **F-RESTORE-RIS / RIS / gap**: Synthetic business-recovery-check gap Context: One shared service supplies recovery to three fictional groups; evidence is reused, not replicated. Supports: RECOVERY-EXERCISE; dissent: none; limitations: none. Mechanism: missing-business-check (supported); sources: RECOVERY-EXERCISE. 
- Source **IAM-COUNTEREXAMPLE**, artifact, version 1, origin IAM-COUNTEREXAMPLE: synthetic://synthesis/IAM-COUNTEREXAMPLE — Worked record IAM-COUNTEREXAMPLE. A separate IAM exercise demonstrated one sign-in transaction. It may not cover registration or research dependencies.
- Source **RECOVERY-EXERCISE**, artifact, version 1, origin shared-restore-exercise-01: synthetic://synthesis/RECOVERY-EXERCISE — Worked record RECOVERY-EXERCISE. One shared restoration exercise restored storage but did not execute a business transaction.

Supplied sample and analyst annotations only; no population prevalence, independence, causal proof, maturity, approval or University finding is established.

## TH-f0df56ec6431

Window: 2026-08-01 to 2026-08-31. Scope: sampled_groups_only. Basis: observed.

Groups not covered by this theme: IAM, RIS.
Related findings outside this theme: F-WAIT-RIS.

Proposed owner role: affected group practice owners.

- **F-WAIT-ESS / ESS / gap**: Synthetic delivery-wait gap Context: Small maintenance change; matched observation window. Supports: ESS-WAIT; dissent: none; limitations: none. Mechanism: handoff-ownership (supported); sources: ESS-WAIT. 
- Source **ESS-WAIT**, metric, version 1, origin ESS-WAIT: synthetic://synthesis/ESS-WAIT — Worked record ESS-WAIT. The supplied trace attributes 120 minutes to waiting for an identified handoff owner.

Supplied sample and analyst annotations only; no population prevalence, independence, causal proof, maturity, approval or University finding is established.

## TH-5b594f42f08e

Window: 2026-08-01 to 2026-08-31. Scope: sampled_groups_only. Basis: observed.

Groups not covered by this theme: ESS, IAM.
Related findings outside this theme: F-WAIT-ESS.

Proposed owner role: affected group practice owners.

- **F-WAIT-RIS / RIS / gap**: Synthetic delivery-wait gap Context: Large test suite; same symptom, different supplied mechanism. Supports: RIS-WAIT; dissent: none; limitations: none. Mechanism: test-worker-queue (supported); sources: RIS-WAIT. 
- Source **RIS-WAIT**, metric, version 1, origin RIS-WAIT: synthetic://synthesis/RIS-WAIT — Worked record RIS-WAIT. The supplied trace attributes 120 minutes to a busy test worker, not an ownership delay.

Supplied sample and analyst annotations only; no population prevalence, independence, causal proof, maturity, approval or University finding is established.

## TH-f8d5ace9cb2d

Window: 2026-08-01 to 2026-08-31. Scope: sampled_all_three_groups. Basis: observed.

Groups not covered by this theme: none.
Related findings outside this theme: none.

Proposed owner role: shared service owner with affected group leads.

- **F-TRACE-ESS / ESS / strength**: Synthetic release-identity strength Context: Same shared trace, three affected groups. Local operation still needs sampling. Supports: SHARED-TRACE; dissent: none; limitations: none. Mechanism: versioned-artifact-map (supported); sources: SHARED-TRACE. 
- **F-TRACE-IAM / IAM / strength**: Synthetic release-identity strength Context: Same shared trace, three affected groups. Local operation still needs sampling. Supports: SHARED-TRACE; dissent: none; limitations: none. Mechanism: versioned-artifact-map (supported); sources: SHARED-TRACE. 
- **F-TRACE-RIS / RIS / strength**: Synthetic release-identity strength Context: Same shared trace, three affected groups. Local operation still needs sampling. Supports: SHARED-TRACE; dissent: none; limitations: none. Mechanism: versioned-artifact-map (supported); sources: SHARED-TRACE. 
- Source **SHARED-TRACE**, artifact, version 1, origin shared-trace-origin: synthetic://synthesis/SHARED-TRACE — Worked record SHARED-TRACE. A shared trace demonstrates source revision to artifact identity for three integration paths.

Supplied sample and analyst annotations only; no population prevalence, independence, causal proof, maturity, approval or University finding is established.

## TH-9d3e60096f4e

Window: 2026-08-01 to 2026-08-31. Scope: sampled_groups_only. Basis: observed.

Groups not covered by this theme: IAM.
Related findings outside this theme: F-REVIEW-IAM.

Proposed owner role: affected group practice owners.

- **F-REVIEW-ESS / ESS / strength**: Synthetic requirements-review strength Context: Manual checklist in a low-frequency workflow; explicit requirements and recheck. Supports: ESS-REVIEW; dissent: none; limitations: none. Mechanism: review-and-recheck (supported); sources: ESS-REVIEW. 
- **F-REVIEW-RIS / RIS / strength**: Synthetic requirements-review strength Context: Automated routing in a frequent-release workflow; equivalent sampled outcome, not a higher maturity score. Supports: RIS-REVIEW; dissent: none; limitations: none. Mechanism: review-and-recheck (supported); sources: RIS-REVIEW. 
- Source **ESS-REVIEW**, artifact, version 1, origin ESS-REVIEW: synthetic://synthesis/ESS-REVIEW — Worked record ESS-REVIEW. Manual review checklist and annotated change show requirements checked and comments resolved.
- Source **RIS-REVIEW**, artifact, version 1, origin RIS-REVIEW: synthetic://synthesis/RIS-REVIEW — Worked record RIS-REVIEW. Automated review routing and annotated change show requirements checked and comments resolved.

Supplied sample and analyst annotations only; no population prevalence, independence, causal proof, maturity, approval or University finding is established.

## TH-70141bd4d04f

Window: 2026-08-01 to 2026-08-31. Scope: sampled_groups_only. Basis: reported_or_mixed.

Groups not covered by this theme: ESS, RIS.
Related findings outside this theme: F-REVIEW-ESS, F-REVIEW-RIS.

Proposed owner role: affected group practice owners.

- **F-REVIEW-IAM / IAM / unknown**: Synthetic requirements-review unknown Context: Fictional example, not a University finding. Supports: none; dissent: none; limitations: none. Mechanism: unknown (unknown); sources: none. No relevant sample supplied. This is not evidence of absent review.

Supplied sample and analyst annotations only; no population prevalence, independence, causal proof, maturity, approval or University finding is established.
