# R04-SHOP-FIRST — reserve shed inventory for live town-shop procurement

**Status:** source + tests + replay-model gate; default OFF; NOT engine-gated
(the pinned engine lacks the shed→shop procurement mechanic — see
GATE-DESIGN.md). Filed as evidence-only carrier; activation requires a
live-canary A/B, never a pinned-engine promotion claim.

## What it does

`r04_shop_first.py` is a pure decision function plus a composer-owned
`ShopLedger`. At the market-order surface, when `cfg["r04_shop_first"] is
True` AND the ledger has observed a live shop tick within the last 48 steps,
positive SELL quantities of shop-demand products are capped so a per-product
reserve floor stays in the shed for shop ticks. Everything else passes
through byte-identical.

Priority (replay-measured absolute $/u): WOOL 123, STRAWBERRY 92, MELON 79,
EGG 52, TOMATO 50, CARROT 49, FERTILIZER 47, WHEAT 42, MILK 40.
Reserve floors: WOOL/STRAWBERRY 24, MELON 20, EGG/TOMATO/CARROT 12,
FERTILIZER/WHEAT/MILK 8.

## Why

Loss forensics (AUTOPSIES-20260912.md, overnight batch): three SHOP-FARMER
losses (eps 108124129 −$6,835, 108114108 −$6,938, 108114745 −$1,086).
Opponents route production through town-shop auto-procurement at 60–4000x
market quotes; we empty the shed into market dumps realizing ~$0.6/u.
Measured shop delta ≈ −$47k in ep 108114745. This is the largest single
untapped edge found in forensics to date.

## Files

- `r04_shop_first.py` — lane module (ShopLedger + filter_market_orders)
- `test_r04_shop_first.py` — unit tests (normal + `python -O` clean)
- `shop_model.py` — replay-derived shop procurement model (the gate)
- `MEASUREMENT.md` — replay evidence for prices/cadence/demand
- `GATE-DESIGN.md` — why no engine gate, model assumptions, results
- `WIRING.md` — composer hook instructions
- `MANIFEST.json` — machine-readable contract

## Test results

- 30 unit checks pass in normal mode and under `python -O`.
- `py_compile` clean on module + tests.
- Replay-derived shop model: DELTA(ON−OFF) = **+$32,811**
  (sensitivity: +$12,578 at $50k demand cap; +$32,464 at $1.20 market;
  +$28,961 at 16u tick cap — positive across all runs).
- Pinned-engine behavior: provably inert (ledger never observes a tick, so
  the filter is a no-op). No pinned-engine regression possible by
  construction; no pinned-engine gain claimed.
