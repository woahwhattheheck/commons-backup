# Steerability Challenge 2026 — public pre-registration foundation

This directory recovers the public-foundation lane originally scoped by **ZNB-R9K4** and implements the offline parts useful before account/Starter-Kit access: deterministic candidate selection, post-selection holdout disclosure, packaging-plan validation, provenance checks, tamper-evident receipts, synthetic fixtures, and a bounded experiment matrix.

It deliberately does **not** pretend to reproduce the organizer's private evaluator or `.spipe` runtime. `dishonesty_reduction` and `capability_regressions` are normalized measurements supplied by an authorized/public evaluator; this code aggregates them transparently. Positive capability changes are not converted into bonuses here—the input must express only actual regression penalties.

## Current public contract (checked 2026-09-14)

The current official competition page describes a steering pipeline as an ordered composition of interventions spanning input/prompt, structure/weights, state/activations, and output/decoding. Standardized `.spipe` submissions are evaluated for reduced dishonesty while preserving general capabilities, with final evaluation on private/held-out tasks. Coding agents are explicitly permitted when entrants can explain their solution. Entrants retain ownership; Apache-2.0 is required only for optional core-toolkit inclusion. The public page lists the final deadline as **2026-11-21 AoE** and says a prize recipient must present **in person or virtually** at the NeurIPS 2026 workshop in Paris. Cash prizes are advertised for first, second, and third; this repository does not claim an amount, win, or payment.

Sources:
- https://steerability.github.io/competition/
- https://steerability.github.io/

A prior guide-v0.2 snapshot cited by the original fleet owner described three target model slots and equivalent pipeline structure with model-specific trained artifacts. `submission_contract.py` therefore defaults to three model slots while making the count an explicit CLI parameter so a later organizer contract can supersede the snapshot without pretending it is immutable.

## What is executable now

```bash
python competitions/steerability-challenge-2026/steerability_foundation.py \
  select competitions/steerability-challenge-2026/fixtures/measurements.selection.json /tmp/selection.json
python competitions/steerability-challenge-2026/steerability_foundation.py verify /tmp/selection.json
python competitions/steerability-challenge-2026/submission_contract.py \
  competitions/steerability-challenge-2026/fixtures/submission-plan.example.json
python -m unittest discover -s competitions/steerability-challenge-2026/tests -v
python -O -m unittest discover -s competitions/steerability-challenge-2026/tests -v
```

Selection is fail-closed against holdout leakage. Candidate comparison is robust-first: worst model mean, then worst row, then mean score, then lower maximum capability penalty, then deterministic candidate ID. A selection receipt binds the exact selection rows before `holdout` will disclose selected-candidate holdout performance.

The submission-plan validator checks safe `.spipe` paths, target-model uniqueness, equivalent intervention structure/configuration across target models while permitting model-specific `*_artifact_ref` values, artifact SHA-256/provenance/license fields, and hard-false registration/submission/private-eval/prize/payment authority.

## Authority boundary

Checked-in public state means only `SOURCE_BUILT_OFFLINE`. It is not evidence of Tally/Hugging Face registration, Starter-Kit access, model downloads, GPU execution, private-evaluation access, organizer acceptance, leaderboard score/rank, workshop commitment, award, payment, or revenue. Those require separately proven provider/human events.
