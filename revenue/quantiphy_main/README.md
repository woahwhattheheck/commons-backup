# QuantiPhy 2026 Main-track hybrid inference harness

This carrier is the **Main track** counterpart to Commons' separate Open-Weight QuantiPhy carrier. The Main track allows proprietary/open/hybrid models; this code does not call any provider itself. Instead it makes model outputs auditable before they can become a competition-shaped submission.

## What it does

1. Validates organizer-shaped validation rows and exact `(video_id, question)` identity.
2. Validates provider/model receipts with immutable request IDs, output/evidence SHA-256, exact integer `cost_microusd`, token counts, latency, status, parsed quantity and optional units. Duplicate exact request replay collapses; changed request-ID reuse fails closed.
3. Refuses ambiguous quantity text (multiple numbers, prose-wrapped values, or unit mismatch) instead of inventing a conversion.
4. Builds complete-model, robust ensemble, and category-router candidates.
5. Uses deterministic **video-grouped** folds so questions from the same video never cross train/validation. Category scales are fit on train folds only, then evaluated on held-out video groups.
6. Enforces a configured exact micro-USD candidate budget before selection.
7. Produces a labels-stripped `submission.csv` from a **separate unlabeled inference/test item set** plus a canonical manifest that binds the fit-time validation hashes, inference/test item and receipt hashes, frozen recipe, selected inference cost, and submission digest.
8. Recompiles the bundle offline. Verification never contacts a provider.

The included public-validation score mirrors the published QuantiPhy MRA shape: absolute positive prediction, relative error thresholds `0.10..0.90, 0.95`, category macro over `S2/D2/S3/D3`. It is **public-validation evidence only** when labels are actually supplied. It is never a hidden-test or leaderboard claim.

## Receipt boundary

Provider credentials, raw API headers, cookies, and tokens do not belong in these files. Identifiers are deliberately restricted. Receipts bind the output by SHA-256 and carry only competition-relevant facts. `REFUSAL`/`ERROR` receipts are preserved but cannot silently become numeric predictions.

An `OK` receipt has the shape:

```json
{
  "schema": "quantiphy-main-receipt/v1",
  "request_id": "REQ-001",
  "provider": "provider-a",
  "model": "model-a",
  "video_id": "video-001",
  "question": "How fast?",
  "status": "OK",
  "output_sha256": "<64 lowercase hex>",
  "parsed_value": "12.5",
  "unit": "mps",
  "prompt_tokens": 100,
  "completion_tokens": 12,
  "latency_ms": 900,
  "cost_microusd": 2500,
  "evidence_sha256": "<64 lowercase hex>"
}
```

## Local synthetic proof

```bash
python -m unittest -v test_quantiphy_main.py
python -O -m unittest -v test_quantiphy_main.py
python -m py_compile revenue/quantiphy_main/*.py test_quantiphy_main.py
```

CLI:

```bash
python -m revenue.quantiphy_main.cli fit validation.json receipts.json \
  --budget-microusd 500000 --folds 4 --recipe-out recipe.json
python -m revenue.quantiphy_main.cli package test_items.json test_receipts.json recipe.json --dest bundle
python -m revenue.quantiphy_main.cli verify test_items.json test_receipts.json bundle/manifest.json bundle/submission.csv
```

## External gates

Checked-in state has no provider/API call, provider credential, registration, terms acceptance, paid spend, hidden/test labels, competition upload, score/rank, award, payment, or revenue claim. A real run must separately establish authorized model/provider access and produce truthful receipts; competition registration/terms and submission remain external actions.
