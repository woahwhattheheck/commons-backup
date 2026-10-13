# TITAN V4 E18 risk-config finite hardening

Status: additive repair custody for the single `main` V4 line. This package does **not** activate gameplay, change defaults/configuration, move `CURRENT`, rebuild an archive, or submit to Kaggle.

## Defect

`revenue/kaggriculture/cloud-execution-lab/selected_sell_core.py` still contains the predecessor E18 numeric parsing blocks on current `main`:

- `float("1e309")` / positive infinity can normalize as `inf / inf -> NaN`; in the expected-downside rule that can bypass the intended positive-expected-gain check.
- several individually finite `1e308` weights can overflow their sum and normalize incorrectly;
- sufficiently large Python integers can raise `OverflowError` during conversion, even under the strict acceptance rule because weights are prepared before rule dispatch;
- an infinite downside bound effectively disables the finite downside budget.

## Narrow semantic repair

The patch adds `_e18_nonnegative_finite()`, maps invalid/non-finite risk inputs to the existing zero fallback, rescales only when a finite set of nonnegative weights overflows its aggregate sum, and applies the same finite parser to `sellDownsideBound`.

Ordinary finite sums retain the historical division sequence. All-zero weights retain uniform fallback. Unknown acceptance rules still fall back to strict. Physical-feasibility rescue is unchanged.

## Preserved evidence

This semantic delta was previously executed against source blob `f23d3a8b5ee5e82029026e7f8f44eb36c143a5a3` before publication access was restored:

- 20/20 focused numeric/native/official-engine checks in normal Python and 20/20 under `python -O`;
- 12/12 source-composition/exclusive-write checks in each mode;
- 216 exact native optimizer comparisons and 1,500 ordinary weight comparisons per numeric run;
- five deliberately broken variants rejected in each mode;
- constructed both-seat terminal witness: predecessor own terminal cash `0`, repaired `5`, rival `0`; this is a correctness witness, **not** a field-EV or strength claim.

The then-concurrent MEADOW receipt-cache transformer composed identically in both orders and passed the same focused numeric suite. Current `main` has since moved, so this package is intentionally a source-bound repair carrier: the existing V4 composer/integrator must rebind/re-run current-stack gates before any runtime promotion.

## Files

- `e18-risk-config.patch` — minimal semantic delta against the preserved predecessor block.
- `compose_e18_risk_config.py` — fail-closed scratch composer; refuses overwrite and unknown/mixed target blocks.
- `test_e18_risk_config.py` — compact hostile checks for finite parsing/normalization invariants.

No sibling V4 root is created. Consume this once through the canonical one-tree integration path.