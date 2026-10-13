# TITAN V5 — current-ABI MICROSTACK H3/S420 re-gate

This directory re-tests the historical H3/S420 hypothesis on the **current**
TITAN seller without resurrecting legacy R04 feature keys or a second policy
tree.

## Historical motivation, not promotion evidence

The recovered V3.1-era stack `{sale_horizon=3,
no_late_sale_advance_step=420}` had a historical controlled receipt of roughly
`+$441` mean margin (`SE $25`, `16/16` positive). That result motivates a fresh
current-V5 re-gate only; it cannot authorize promotion.

## Canonical current-ABI interpretation

The authoritative current-source transform already landed in
`candidates/v4/research/sale-window-engagement/compose_current_h3s420.py`
(Git blob `7c5778b4d6d7c47f8feca7e800fc8093267b66f8`, source repair #12859).
This carrier authenticates and reuses that exact source-rewrite theorem on the
pinned current `frozen_selected.py` postimage instead of defining another S420
adapter.

Arms:

* **control** — current `frozen_selected.py` bytes unchanged;
* **H3** — only the inherited baseline `HORIZON` is shadowed from `8` to `3`;
  current public service/unit extensions and materialization remain intact;
* **H3+S420** — apply the exact canonical composer semantics: H3 plus, at
  `step >= 420`, skip the **entire new-plan-selection block**. Inherited/base
  SELL rows and already-planned due quantities still flow through the untouched
  materialization tail.

There is deliberately no equal-total-only exception, no non-comparable-plan
fail-open, and no forced-feasibility bypass at/after the canonical S420 cutoff.
Those were a second theorem and are excluded by `SOURCE-PINS.json`.

## Source custody

`SOURCE-PINS.json` binds exact current `frozen_selected.py`,
`selected_sell_core.py`, and `scheduler.py` blobs plus the canonical H3/S420
composer blob. `test_source_pins.py` fails closed on drift. The behavior suite
also executes a direct step-420 predecessor where a quantity-changing new plan
would be produced: canonical S420 must skip that block completely, while the
same block remains reachable before the threshold.

## Focused checks

From this directory:

```bash
python -B -m unittest -v test_current_sale_timing.py test_source_pins.py
python -O -B -m unittest -v test_current_sale_timing.py test_source_pins.py
python -m py_compile current_sale_timing.py test_current_sale_timing.py test_source_pins.py
```

Hosted CI checks out and asserts the exact PR event head before running those
contracts on Python 3.11 and 3.12.

## Evaluation contract

The next gate is matched current-V5 official-engine evidence using the same
source/package identity for all arms. A runner should materialize the three
isolated source arms through `compose_current_frozen(...)`, run both seats
against strong authenticated opponents, and record per-cell own/rival/margin,
first returned-action divergence, engagement, failures, timing, and the
`canonical_semantics_receipt()` identity. Promotion requires fresh current-V5
economics and the shared paired-economics firewall.

## Hard boundaries

No production `Features` key, `TITAN-CONFIG.json` edit, release archive/pointer
mutation, legacy R04 router/materializer, second seller/controller, or Kaggle
submission belongs in this directory. Any winner must converge through the one
current V5 runtime after moving-main review.
