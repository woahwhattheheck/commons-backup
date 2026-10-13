# CAS-style actuarial LLM benchmark reproducibility core

This package is a **buyer-neutral, synthetic benchmark mechanics layer** shaped around the public Casualty Actuarial Society 2026 RFP for a repeatable P&C perception/classification benchmark. It demonstrates deterministic task/data identity, objective scoring, repeatable re-testing, uncertainty intervals, and comparison-board publication. It contains no CAS dataset and makes no claim that its synthetic tasks are actuarially valid.

## What is bound

A suite fixes the suite/version, dataset SHA-256, declared license/provenance route, task identities, prompt hashes, gold labels, class labels/weights, scoring policy, probability floor, and deterministic bootstrap policy. A run fixes the exact suite/dataset identity, model/provider/version/config digest, adapter version, prompt-policy digest, and one canonical probability vector for every task/item.

The scorer fails closed on missing/unknown items, task/dataset/version mismatch, changed-payload duplicate predictions, or label-set drift. Exact duplicate/reordered predictions collapse to the same run digest and receipt.

## Objective metrics

For each task and the declared weighted aggregate, the core emits:

- accuracy;
- macro F1;
- multiclass Brier score (sum-of-squared class probability errors per item);
- natural-log loss using the suite-declared probability floor;
- deterministic bootstrap confidence intervals for all four metrics.

All probabilities are canonical decimal strings that must sum exactly to one. Metric outputs are quantized to 12 decimal places. Confidence intervals are seeded from the exact suite/run digests and bootstrap policy so re-running the same evidence produces the same receipt.

`build_board()` accepts only READY receipts for the exact suite digest and emits a deterministic comparison board ranked by the declared primary metric with stable tie-breakers. Receipts and boards are content-addressed and can be re-evaluated with `verify_receipt()` / `verify_board()`.

## Validation

```bash
python -m unittest revenue.cas_actuarial_llm_benchmark_core.test_benchmark -v
python -O -m unittest revenue.cas_actuarial_llm_benchmark_core.test_benchmark -v
python -m revenue.cas_actuarial_llm_benchmark_core.acceptance
```

The acceptance fixture uses **24 synthetic items across 3 classification tasks and 7 synthetic model runs**. It proves deterministic ranking/replay plus four deliberate HOLD paths: missing item, unknown item, same-ID changed prediction, and wrong dataset digest.

## Authority boundary

`AUTHORITY = REPRODUCIBILITY_ONLY_NO_ACTUARIAL_VALIDATION` is intentional. This core does **not**:

- assert that any task/dataset is actuarially sound, representative, uncontaminated, legally publishable, or approved by CAS;
- call OpenAI, Anthropic, Google, or an open-source model endpoint;
- make model-quality claims from the synthetic acceptance fixture;
- clear dataset copyrights/licenses or substitute for actuarial SME review;
- implement CAS's final public web UI, proposal submission, pricing, contracting, or buyer acceptance.

Those are separate scientific, actuarial, legal, product, and commercial workstreams. The point here is to make the benchmark mechanics inspectable and reproducible before those authorities are attached.
