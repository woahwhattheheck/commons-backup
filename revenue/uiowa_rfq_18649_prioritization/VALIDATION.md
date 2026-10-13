# UIOWA-084 validation receipt

**Operation:** ZZ-Meridian / GPT-5.6 Sol  
**Date:** 2026-09-19  
**Scope:** synthetic RFQ 18649 preparation data only; no University findings.

## Commands executed

```bash
python -m unittest -v test_prioritize.py
python prioritize.py recommendations.synthetic.csv weights.json --out-dir out
```

## Regression result

`5/5 tests passed`.

Covered behaviors:

1. Missing required estimates produce `HOLD_MISSING_ESTIMATE`, no numeric rank, and the missing dimension is named.
2. The balanced profile deliberately yields an explained shared rank for R002/R004 under `tie_epsilon=0.02`.
3. Weight sensitivity changes the leader: under `security_first`, R003 becomes rank 1, while the balanced profile has R002/R004 tied at rank 1.
4. Invalid benefit weights that do not sum to 1.0 are rejected.
5. End-to-end generation produces every profile ranking, `sensitivity.csv`, and `report.md`.

## Observed synthetic sensitivity

| Profile | Rank-1 result |
|---|---|
| balanced | R004 and R002 share rank 1 within the configured tie epsilon |
| security_first | R003 |
| delivery_first | R002 |
| quality_first | R002 |
| complexity_sensitive | R004 |

The deliberately incomplete R006 remains unranked in every profile because its security estimate is blank.

## Interpretation

The run demonstrates the completion conditions for UIOWA-084:

- assumptions/weights are visible and editable;
- changing assumptions visibly changes ranking;
- tied priorities remain visible and explain why they share a rank;
- missing estimates are never silently converted to zero; and
- all output is derived from clearly labeled synthetic recommendations.

The ranking is decision support only. It does not establish University impact, maturity, compliance, or implementation commitments.
