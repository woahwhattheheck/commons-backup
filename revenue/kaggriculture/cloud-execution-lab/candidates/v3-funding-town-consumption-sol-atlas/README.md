# TITAN V3 funding town-consumption closure

This candidate closes one exact projection gap in the current selected SELL
runtime. `funded_minimum_now(...)` protects inherited market acquisitions by
replaying the represented market tape through `_funding_trace(...)`. The current
trace applies unit actions and market orders but omits the official engine's
deterministic public town-consumption stage after each turn. That can understate
future `BUY_PRODUCT` prices and certify withholding a current sale that is
actually needed to fund an inherited purchase.

The first reviewed carrier correctly modeled the current public shop set, but an
independent exact-head review found that this set can change at a day close. A
newly unlocked shop can consume product before a later inherited purchase. The
successor therefore has two deliberately narrow rules:

1. within the current day, replay the exact current public shop multiset after
   every represented market stage;
2. if the protected horizon crosses a day boundary, fail closed to the inherited
   current sale quantity instead of guessing future shop RNG or count evolution.

The carrier is additive and default-off. It does not modify the canonical
runtime. It byte-binds the exact current `frozen_selected.py` Git blob, inserts a
small official-order-equivalent helper and lifecycle guard, verifies the exact
official interpreter and market→town→decay stage order, compiles the postimage,
and emits a strict JSON receipt.

## Same-day predecessor

Public state and inherited route:

- current step: `0`;
- current cash: `$31`;
- market WHEAT inventory: `10000`;
- eight unlocked `BAKERY` instances;
- one MILK unit in the shed and a current `SELL MILK 1`;
- inherited `BUY_PRODUCT WHEAT 1` at step `22`;
- default shop interval `4`, town-center interval `24`;
- current funding stress: `32` WHEAT units.

The predecessor omits town consumption. Under its stress-only projection, the
step-22 WHEAT purchase is quoted at `$31`, so it reports `minimum_now=0` and may
withhold the MILK sale.

The official stage consumes WHEAT after market processing at steps
`0,4,8,12,16,20`: eight BAKERies consume 48 units, and the town center consumes
one more at step 0. The exact pre-purchase inventory is therefore `9951`; a
WHEAT buy quotes the post-buy inventory `9950`, costing `$32`. With only `$31`,
the inherited purchase fails unless the current MILK sale is retained. The
successor reports `minimum_now=1` without fallback.

## Cross-day lifecycle predecessor

The reviewed step-71→77 case starts with `$26`, WHEAT inventory `10000`, a
current MILK sale, and a future `BUY_PRODUCT WHEAT 1` at step 77. The public shop
set observed at step 71 is not a valid projection through the day close: a new
BAKERY can unlock before town stages 72 and 76. A frozen-shop trace quotes the
future buy at `$26` and releases the current sale; the evolved shop set quotes it
at `$27`, so the acquisition fails.

The successor does not attempt to reconstruct hidden future shop selection. The
step-71→77 horizon crosses `turnsPerDay=24`, so `_funding_trace()` raises inside
the existing certificate boundary. `funded_minimum_now(...)` then returns the
inherited current quantity with `fallback=true`: `minimum_now 0 → 1` for the
review predecessor.

## Closure

Pinned objects:

- source Git blob: `fc7baf5c179818a55037f6a61d92984d81d1a21c`;
- official engine Git blob: `3c202c7ee921da239356789e266b694635103fc4`.

The generated patch:

1. rejects malformed, boolean, fractional, or nonpositive `turnsPerDay`;
2. rejects every funding horizon whose start and end fall on different days;
3. after every same-day projected market stage, applies every currently
   unlocked shop instance;
4. preserves duplicate shops;
5. applies the official two-unit multiplier to single-product shops;
6. applies the town center on its configured interval;
7. excludes FERTILIZER from town-center consumption;
8. preserves the existing rival `stress_units` scenario as additional pressure;
9. fails closed through the existing funding-certificate fallback on malformed
   public shop state.

## Validation

From this directory:

```bash
python -m unittest -v test_town_consumption_closure.py
python -m py_compile town_consumption_closure.py test_town_consumption_closure.py
python town_consumption_closure.py \
  --source ../../frozen_selected.py \
  --engine ../../reference/engine/kaggriculture.py \
  --output /tmp/frozen_selected_town.py \
  --receipt /tmp/town-consumption-receipt.json
python -m py_compile /tmp/frozen_selected_town.py
```

The contracts cover exact source/engine closure; the same-day
`minimum_now 0 → 1` predecessor; the reviewed cross-day lifecycle
`minimum_now 0 → 1` fallback; official `$31 → $32` price separation;
duplicate and single-product shop semantics; town-center/FERTILIZER behavior;
no-event identity; malformed shop and day-length fail closure; postimage
compilation; and strict receipt serialization.

No hosted strength, release selection, canonical-runtime, provider, Kaggle, or
submission claim is made. After independent source review, the one-tree owner
should consume only the generated postimage and run action-active, paired
official-engine regression cells before promotion.
