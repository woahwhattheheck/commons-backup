# DEMANDVEL — Gemini/Antigravity demand velocity, upgraded for V4

This is a **source-bound research/admission extension** inside the existing `market-baseline` authority. It does not create a crop chooser, demand forecaster, controller, feature key, runtime path, default, archive or Kaggle mutation.

Pinned source remains the baseline's official engine blob `3c202c7ee921da239356789e266b694635103fc4` and spec blob `b354d06b742fe48402513792253f1a5c29366b20`.

## What Gemini got right

For one uniformly drawn shop instance on one town shop-consumption tick, the exact expected drain is:

| product | units / shop-instance tick |
|---|---:|
| WHEAT | 0.625 |
| STRAWBERRY | 0.500 |
| CARROT | 0.375 |
| MILK | 0.375 |
| TOMATO | 0.250 |
| EGG | 0.250 |
| WOOL | 0.250 |
| MELON | 0.000 |
| FERTILIZER | 0.000 |

The singleton `PET_CAFE` and `YARN_STORE` consume two units per tick, which is why CARROT and WOOL are higher than a naive shop-count fraction would imply.

## What the raw tier rule omitted

Those ratios are **not a safe production cap**. Four source facts materially change the answer:

1. shop instances unlock only on days 3,6,9,12,15,18,21,24, so early instances get far more consumption ticks than late ones;
2. shops are sampled **with replacement**, creating large per-seed tails;
3. the town center removes one of every non-FERT product every 24 steps, including MELON;
4. opponent supply and sale timing compete for the same demand headroom, so terminal NPC absorption does not certify profitability or a safe early sale.

Closed-form expectation over uniform replacement draws for the 719 action-bearing callbacks is therefore:

| product | expected full-episode NPC depletion |
|---|---:|
| WHEAT | 525 |
| STRAWBERRY | 426 |
| CARROT | 327 |
| MILK | 327 |
| TOMATO | 228 |
| EGG | 228 |
| WOOL | 228 |
| MELON | 30 |
| FERTILIZER | 0 |

The existing exact-RNG 100-seed baseline is intentionally retained as the stronger empirical distribution. Its p10 final-depletion floor is:

| product | p10 NPC absorption |
|---|---:|
| WHEAT | 354 |
| STRAWBERRY | 174 |
| MILK | 100.2 |
| EGG | 84 |
| TOMATO | 66 |
| CARROT | 30 |
| WOOL | 30 |
| MELON | 30 |
| FERTILIZER | 0 |

The tail result is the important upgrade: expected CARROT/WOOL demand can look respectable while a material shop-multiset tail supplies essentially only the 30 town-center units. A fixed “tier-2/tier-3” production quota would hide that risk.

## V4 primitive

`demand_velocity.py` exposes three layers without claiming policy authority:

- `per_shop_instance_velocity()` — the exact Gemini ratios;
- `closed_form_expected_depletion()` — adds unlock horizon and town-center demand;
- `panel_absorption()` / `conservative_headroom()` — converts the existing source-exact baseline into low-quantile terminal absorption headroom.

`conservative_headroom()` always returns `decision_authority=false`, `timing_authority=false`, and `opponent_supply_accounted=false`. A consumer may use the budget as one crop-mix or scaling admission input, but must still account for rival supply, current public inventory, service capacity, cash, shed/carry capacity, market-row ownership, and the timing of sales versus future town demand.

## Composition handoff

- **DEMAND-CURVE** keeps forecasting ownership.
- **CROPSCALE** keeps service/action-capacity ownership.
- **MELON cap** keeps its current default-OFF quota experiment and should consume this only as evidence that MELON has center-only demand, not as promotion authority.
- **market-pressure / sale-window / TOWNSELL** keep sale timing and rival-flow ownership.

This is the best-form V4 interpretation of the Antigravity DEMANDVEL exploit: preserve the exact source insight, replace the brittle hard tiers with quantified absorption tails, and make the result composable without introducing another controller.
