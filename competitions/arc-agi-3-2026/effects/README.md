# SAGE causal-effect factorizer

Post-SAGE ARC-AGI-3 research carrier. This package decomposes **observed visual transitions** into reusable effect evidence instead of treating every changed frame as one opaque digest.

It deliberately does **not** claim that an action is the unique physical cause of a visual change. Camera motion, UI updates, animation, global shifts, compound effects, and low-evidence cases are retained as separate or ambiguous explanations.

## Taxonomy

- `MOTION` — same-color normalized component shape translated locally.
- `SPAWN` / `DESPAWN` — unmatched non-background components.
- `RECOLOR` — identical occupied cells change color.
- `TOPOLOGY` — spatially continuous same-color region changes component count (split/merge).
- `UI` — >=80% of changed cells are on the one-cell frame border and no camera explanation wins.
- `CAMERA` — at least two independent matched components share one nonzero translation covering >=70% of prior foreground area.
- `COMPOUND` — more than one observed effect family is present.
- `NO_CHANGE` / `AMBIGUOUS` — explicit null/insufficient-explanation states.

Every pair result carries exact before/after hashes, confidence basis points, and component witnesses. `factor_action()` retains each intermediate animation-frame transition rather than comparing only final frames.

## SAGE integration

`sequence_from_transition()` consumes the landed SAGE `Transition` duck contract (`before.frame`, `action.key`, `after.frames`) without mutating `WorldModel` or policy and without any `ACTION1 == UP`-style semantic table.

```python
from effects.sage_adapter import factor_transition

effect = factor_transition(sage_transition)
```

The adapter preserves coordinate-action keys such as `ACTION6@2,3` and every retained post-action frame.

## Deterministic proof

From this directory:

```bash
PYTHONPATH=. python -B -m unittest -v test_effects.py
PYTHONPATH=. python -O -B -m unittest -v test_effects.py
PYTHONPATH=. python benchmark.py --seeds 100
```

Pre-publication implementation: 23/23 tests PASS normally, 23/23 under `python -O`, compile PASS, and the held-out generator reports 900/900 cases across all nine tested families with receipt `399268b72833b5518d39a27cc1a1f55b644d016e7fb71e7ae55ce7181c22a183`.

The synthetic benchmark is only a taxonomy/wiring invariant. It is **not** an ARC public/private score, Kaggle score, competition submission, rank, award, payment, or revenue claim.

## Receipt boundary

`receipts.py` recomputes the factorization from supplied exact frames and requires all authority fields to remain false: unique physical causality, official ARC score, competition submission, provider/device action, prize/payment/revenue. Re-sealing the outer digest after elevating an authority bit still fails semantic verification.
