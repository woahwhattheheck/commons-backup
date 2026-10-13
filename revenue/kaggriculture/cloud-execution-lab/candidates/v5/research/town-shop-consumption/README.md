# V5 town-shop consumption semantics

Research-only correction against the official reference engine blob
`3c202c7ee921da239356789e266b694635103fc4`.

## Result

The town-demand mechanism is real, but two details in the V5 idea feed were
misstated:

1. **Shops do not unlock nightly at the default configuration.**
   `townShopUnlockInterval` defaults to 3 days, with one shop instance drawn
   with replacement at days 3, 6, 9, ... until the eight-instance cap.
2. **BAKERY and BRUNCH_SPOT do not receive a 2x multiplier.**
   `_town_consume` uses `2 if len(products) == 1 else 1`. The only doubled
   shops are `PET_CAFE` (CARROT) and `YARN_STORE` (WOOL). BAKERY and
   BRUNCH_SPOT each consume one EGG per shop tick.

At the default 24 turns/day and 4-turn shop interval, each EGG-consuming shop
therefore removes **6 EGG/day**. The town center removes one additional EGG/day.
Through day 8, at most two shop instances have unlocked, so even the all-EGG
composition has an upper bound of **13 EGG/day total** (12 from shops + 1 town
center). Once the full eight-shop cap is reached, the absolute all-EGG upper
bound is **49 EGG/day**.

Thus a later 37+ EGG/day realization is possible only with enough unlocked
instances and an EGG-heavy random composition. It is not caused by a doubled
BAKERY/BRUNCH multiplier and cannot occur by day 8 under the default cadence.

## Why it matters

Projection and market-timing work should model realized `town.unlocked_shops`
instance-by-instance instead of assuming a generic 12-unit/day shop drain.
The same rule makes single-product CARROT/WOOL shops structurally stronger:
under the eight-shop cap their extreme per-resource upper bound is 97/day
including the town center, versus 49/day for EGG and other one-unit shop goods.
MELON has no dedicated shop demand in this engine and receives only the town
center's 1/day; FERTILIZER receives neither.

## Verification

`verify_town_shop_consumption.py` parses the checked-in official engine as data,
checks the source-facing unlock/consumption seams, reads the official config
defaults, and derives the bounds. `test_town_shop_consumption.py` freezes the
correction as focused regression assertions without importing Kaggle.

This package does not alter TITAN runtime behavior, defaults, configuration,
archives, opponent policies, simulation ownership, or Kaggle submission state.
QUILL #4 RNG steering remains a separate lane.
