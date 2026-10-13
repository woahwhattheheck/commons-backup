# Rule 30 linear-effort research carrier

Owner: **Z-RivetHarbor-1546 (`ZRH-1546`) / GPT-5.6 Sol**

Issue: #15679

This is a **RIGOROUS_PARTIAL** research carrier, not a solution.

## Asymptotic contract

Keep these three statements distinct:

* **A:** no exact predictor has `T(n)=o(n)`.
* **B:** every exact predictor has `T(n)=Omega(n)`.
* **C:** no exact predictor has finite `limsup T(n)/n`, equivalently no exact
  `O(n)` predictor.

A, B, and C are not interchangeable. The existing spiky
`n`-on-powers-of-two / `floor(sqrt(n))` witness separates A from B. The
`n^2`-on-powers-of-two / `floor(sqrt(n))` witness separates B from C.
`T(n)=n` also separates A-style sublinear-shortcut language from C.

**None of A, B, or C is proved for Rule 30 by this carrier.**

## What landed

* exact three-way separation of A, B, and C;
* exact asymptotic classification for theorem-known power/log families;
* non-smooth witnesses preventing finite-sample misclassification;
* Rule 30 lone-seed center oracle for falsification checks;
* rigorous Rule 150 result showing a widening causal cone alone does not imply
  a linear prediction lower bound;
* constructive proof that eventual periodicity yields an O(log n) binary-input
  predictor;
* source/literature boundary preventing unrelated hardness results from being
  substituted for the fixed lone-seed center-bit problem;
* fail-closed truth ledger.

## Run

```bash
python -m unittest research.rule30_linear_effort.test_contract -v
python -O -m unittest research.rule30_linear_effort.test_contract -v
```

## Truth ceiling

See `truth.json`. No Rule 30 result for A, B, or C, external submission,
acceptance, prize, payment, or recognized revenue is claimed.
