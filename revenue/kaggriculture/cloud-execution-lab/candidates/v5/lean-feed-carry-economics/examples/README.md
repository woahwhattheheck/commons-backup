# Synthetic contract fixtures

These fixtures exercise the evidence and promotion-fence contracts only. They are **not TITAN engine results** and must never be cited as empirical promotion evidence.

Generate the README-named inputs deterministically from the package test-contract helper:

```bash
python examples/generate_synthetic_contracts.py
```

- `synthetic_positive_contract.json` contains a complete synthetic causal chain. The candidate economics evaluator supports `PROMOTE_RESEARCH_CANDIDATE`, but the official CLI must emit final `SOURCE_MODEL_BLOCKED` and suppress synthetic economic arrays while exact D2 source custody remains unavailable.
- `synthetic_no_redeployment.json` removes downstream use of liberated cash and must emit candidate and final `NO_PROMOTION`.

The checked-in `positive-cli.json` and `negative-cli.json` files are historical output examples from the pre-hardening candidate contract; they are not promotion-authority receipts.
