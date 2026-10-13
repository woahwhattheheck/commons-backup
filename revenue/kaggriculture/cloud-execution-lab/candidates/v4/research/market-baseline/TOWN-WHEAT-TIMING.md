# TOWNFLASH — source-bound WHEAT town-event timing

Research-only successor inside the existing V4 `research/market-baseline` authority.

## Result

Pinned official engine Git blob `3c202c7ee921da239356789e266b694635103fc4` resolves each callback in this order: **unit actions → market → town consumption**. `BUY_PRODUCT WHEAT` is quoted at post-buy inventory. The town then subtracts the current public shop demand (every configured shop interval) and the town-center unit (every configured center interval). Therefore an already-needed WHEAT purchase made immediately **before** a known town drain cannot cost more than the identical purchase delayed until after that drain on the standard monotone WHEAT curve.

Exact constructed source-bound witness at public inventory 10,000, step 100, and five currently unlocked WHEAT-consuming shop instances: buying 100 WHEAT before the town phase costs `$3,170`; the same 100 bought immediately after the deterministic 5-unit town drain costs `$3,212`, a **$42 timing advantage**. A mechanism-only buy-before/sell-after round trip under **zero rival WHEAT flow** returns the same +$42; with zero town demand the unchanged-market round trip is exactly $0, matching the engine's post-buy quote design.

The test grid checks inventories 8,000–12,000, demand 0–9, and quantities 1/5/20/50/100 against the exact engine pricing function: no deterministic-demand procurement window or zero-rival round trip is negative on those 300 cells. The oracle also rejects an impossible public shop list longer than the engine's exact `MAX_SHOP_INSTANCES` cap rather than fabricating excess town demand.

## What this does not prove

This is not a speculative trading recommendation and not current-native EV. Rival WHEAT flow can alter realized inventory between the two callbacks. Cash, shed room, feed obligations, market-row ownership, and the usefulness of holding/reselling WHEAT remain external policy constraints. The safer downstream consumer is **timing an already-authored/required WHEAT acquisition**, not adding inventory merely because a town tick is imminent.

`ASTRA-DEMAND-CURVE` retains demand/forecast ownership. Existing WHEAT merchant owners retain trading-policy ownership. A current-native consumer should shift eligible purchases only when it preserves quantity, feed reserve, cash/capacity safety, and authored market rows.
