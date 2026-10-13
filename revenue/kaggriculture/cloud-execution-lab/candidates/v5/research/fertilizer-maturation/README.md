# V5-24 fertilizer maturation / negative-age audit

This package executes V5 seed #24 against the pinned official Kaggriculture
engine (git blob `3c202c7e...`, SHA-256 `bc8a5487...`). The proposed
"fractional growth overdose" / negative-maturation exploit is **falsified**.

The official `FERTILIZE` action does not alter `planted_day`,
`max_lifespan_step`, or `yield_units`. It consumes one fertilizer and only
extends `fertilized_until_day` to `max(existing, day + 2)`. Repeating the action
on the planting day therefore burns additional fertilizer while leaving the
same three-day fertilizer window; the window does not stack.

Harvest maturity is still checked independently against
`day - planted_day < first_yield_day`. The executable probe applies fertilizer
four times on the planting day to both CARROT (non-ongoing) and TOMATO
(ongoing), then attempts an immediate harvest. CARROT keeps its initial latent
yield but cannot be harvested early; TOMATO still has zero yield. Neither crop's
clock moves.

The useful engine fact is narrower: fertilizer is a temporary yield bonus on
eligible watered production, not a maturation-time accelerator.

Run from this directory:

```bash
python3 -m unittest -v test_fertilizer_maturation.py
python3 verify_fertilizer_maturation.py
```

No TITAN runtime, policy/default, archive, opponent, seed panel, or Kaggle state
is changed.
