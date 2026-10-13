# TITAN V4 CROSSFLOW — opposite-side lockstep market quotes

**Disposition: SOURCE MECHANICS ONLY / no timing-policy or EV claim.**

This packet lives inside the existing `research/market-baseline/` authority. It covers the same-item `BUY_PRODUCT` ↔ `SELL` seam for WHEAT/FERTILIZER. It does not create a controller, runtime key, sibling V4, default/config/archive/Kaggle mutation, or rival-current-action predictor.

## Theorem

Pinned official engine Git blob: `3c202c7ee921da239356789e266b694635103fc4`.

Within each raw market row the engine quotes both players from the same pre-commit public inventory. A SELL unit uses `price(I)`; BUY_PRODUCT uses `price(I-1)`. Commits happen only after both quotes are formed. Away from the destructive `$1` SELL floor, one same-item SELL plus one BUY returns public inventory to the same terminal state, but alignment freezes both players at stale pre-opponent quotes.

For already-required flows, delaying a BUY one raw row until after rival supply is weakly cheaper; delaying a SELL one raw row until after rival demand is weakly more valuable. This is mechanics evidence only. Any policy consumer still needs an independently observable/authored alignment opportunity plus row-cap, cash, shed, and composition custody.

## Exact default witnesses

At inventory 10,000 and quantity 100:

| item | aligned BUY | delayed BUY | saving | aligned SELL | delayed SELL | gain |
|---|---:|---:|---:|---:|---:|---:|
| WHEAT | 2600 | 2193 | **407** | 2500 | 3170 | **670** |
| FERTILIZER | 10000 | 9010 | **990** | 10000 | 11010 | **1010** |

At the `$1` SELL floor the clean same-terminal theorem explicitly refuses because official SELL semantics destroy the private unit without returning it to public inventory.

## Recovery note

This is the fresh-main recovery of stale PR #12936. The original carrier contained a literal syntax corruption in `_plain_inventory` despite its body claiming py_compile success. The recovery rewrites the small oracle cleanly, preserves the theorem and exact witnesses, and validates the actual authored bytes before publication.

## Validation

Executed on the exact recovery bytes:

- `python -m unittest -v test_crossflow_quote_oracle.py`
- `python -O -m unittest -v test_crossflow_quote_oracle.py`
- `python -m py_compile crossflow_quote_oracle.py test_crossflow_quote_oracle.py`

The repository-engine test is checkout-gated and pins the exact engine Git blob. Isolated tests use a source-faithful two-product market subset.
