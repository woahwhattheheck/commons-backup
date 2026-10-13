# Feed-stock × four-feature interaction cross

This is an additive causal extension of the existing submitted-V4 four-feature factorial. It exists because the two landed self-ablation families do not observe their aggregate interaction:

- the four-feature factorial disables `idle_fertilizer`, `crop_release`, `early_capital`, and `town_procurement` while the V4 WHEAT feed-stock reservation remains enabled;
- the feed-stock ablation disables only `TitanAgent._feed_stock_selected()` while the four selected V4 booleans remain enabled.

The missing corner is therefore `feed_stock_off + all_four_off`. A positive or negative interaction can be invisible to either one-factor-family screen.

## Exact 2×2 design

The source helper `feedstock_fourflag_cross.py` composes only the two existing treatment authorities and exposes four arms:

| arm | feed-stock | four selected flags |
| --- | --- | --- |
| `v4` | ON | ON |
| `feed_stock_off` | OFF | ON |
| `all_four_off` | ON | OFF |
| `both_off` | OFF | OFF |

The helper pins the landed factorial donor and feed-stock materializer by Git blob and executes only their captured source bytes. It accepts only the exact submitted-V4 archive authority shared by both donors.

The changed-member contract is fail-closed:

- `v4`: no changed members;
- `feed_stock_off`: only `titan_runtime.py`;
- `all_four_off`: only `TITAN-CONFIG.json`;
- `both_off`: exactly `titan_runtime.py` plus `TITAN-CONFIG.json`.

`operating_stock.py` must remain byte-identical in every arm. The combined arm must reuse the exact runtime bytes from `feed_stock_off` and the exact config bytes from `all_four_off`; this helper does not invent a third treatment.

## Interaction statistic

For any paired outcome value `Y`, the interaction is

`Y(both_off) - Y(feed_stock_off) - Y(all_four_off) + Y(v4)`.

The helper also reports both conditional feed-stock effects, both conditional four-feature effects, and the joint effect relative to V4.

## Execution boundary

This commit is source/evidence plumbing only. It deliberately does **not** modify the existing six-arm game runner, because that runner is already queued for official-engine work. Game execution for this cross must reuse the canonical authenticated feed-stock custody successor and the existing factorial harness after their exact source gates are green. No runtime/default/CURRENT/archive pointer/release/Kaggle mutation is authorized here.

Do not expand this into a 32-arm five-factor experiment. The purpose is only to test the single missing aggregate corner before spending more simulator capacity.
