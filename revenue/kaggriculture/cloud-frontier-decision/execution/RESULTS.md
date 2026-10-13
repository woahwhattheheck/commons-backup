# Completed development ablation: reject both execution variants

24 official-engine cloud games completed without failures: exact Arlene control, cap-only, and cap plus public-demand release, each on seeds 9600701/9600719 against Arlene/Apex in both seats. No rerun of the prior Breaking the Tie fixture panel. Development source was unchanged across these games. Held seeds 9600751/9600769 remain unused because neither candidate earns promotion from development.

| Mode | vs Arlene W/T/L | vs Apex W/T/L | Paired outcome flips from baseline |
| --- | --- | --- | --- |
| Intact Arlene | 0/4/0 | 2/0/2 | control |
| Cap-only | 0/2/2 | 2/0/2 | 2 T→L, zero improvements |
| Cap + demand release | 0/0/4 | 2/0/2 | 4 T→L, zero improvements |

Margin diagnostics, own terminal cash minus rival terminal cash:

| Mode | Arlene mean margin | Apex mean margin |
| --- | ---: | ---: |
| Intact Arlene | 0 | 1125 |
| Cap-only | -101 | 1010 |
| Cap + demand release | -161.5 | 961.5 |

Both seats produced the same cash pairs for each seed/opponent/mode in this panel. Compact cash pairs below are own/rival regardless of seat; full per-seat rows are in results/summary.json.

| Seed | Opponent | Baseline | Cap-only | Cap + demand |
| --- | --- | --- | --- | --- |
| 9600701 | Arlene | 86726 / 86726 | 86648 / 86850 | 86614 / 86900 |
| 9600701 | Apex | 86893 / 89000 | 86875 / 89212 | 86854 / 89251 |
| 9600719 | Arlene | 96959 / 96959 | 96959 / 96959 | 96942 / 96979 |
| 9600719 | Apex | 97933 / 93576 | 97933 / 93576 | 97916 / 93596 |

## Discriminating observations

All 16 candidate/control pairs have identical own unit-action counts, successful market quantities, and terminal private stock. Thus these losses are not explained by selling fewer total goods or leaving more terminal stock. Passive same-observation comparison covers all 719 turns per game: zero changes to parent unit actions or non-SELL orders. This verifies the overlay boundary; aggregate counts alone are not a full cross-game action-sequence equality proof.

On seed 9600701 against Arlene, cap-only changes own MILK receipts by -75 and CARROT by -3; own cash is -78 while rival cash is +124 in the paired run. Demand release reduces own MILK receipts by -109 and CARROT by -3; own cash is -112 while rival cash is +174. Against Apex, cap-only improves own MILK receipts by +19 but loses 38 STRAWBERRY cash and gains 1 CARROT cash, ending -18 own cash. The rival ends +212, so own receipt improvement in a single product does not establish a better game outcome.

On seed 9600719 cap-only is cash-neutral. The demand addition reduces own STRAWBERRY receipts by 12 and MILK by 5 against both opponents, with rival cash +20. Known demand can raise the no-rival counterfactual quote, but these completed interactions do not reward that waiting rule. No scenario probabilities or causal opponent-revenue estimator were invented.

The conservative capacity override deliberately limits how often the cap acts: market output differs from same-observation Arlene on 22 turns per game on seed 9600701; on seed 9600719, cap-only differs on one turn and demand on six. This is a bounded implementation result, not a finding that all depth-capped execution algorithms fail.

## Evidence and reproducibility

Nine focused tests pass: band/fraction sizing, parent-lot/stock bounds, same-turn split budget, observed versus unavailable fills, deadline and day-close overrides, purchase dependency, capacity override, fixed demand release, and a price-floor-then-town-consumption receipt. The latter pays 3+2+1+1 with only two admitted supply units, then after consumption of two pays 3 again: total 10, not 8.

Maximum recorded candidate call across all 24 games was 18.40 ms in this cloud run. Full raw per-game actor timing, diagnostics, terminal state, daily snapshots and trace digests are preserved in results/{baseline,cap,demand}.json.gz. Summary pins the exact engine, evaluator, harness, source modules, and parent build. Arlene source is 1dc166ae2bf0c56a44fac4482f469b8812968c4cb32459cb9860f5077897a7d4; Apex source/native build pins are retained in the runtime manifest. No broad leaderboard or optimality claim follows from two seeds.

Selection: retain intact Arlene as production foundation. Merge this coherent research source and evidence without composing or promoting it. Share the reservation and quantity-receipt interface with the independent finite-horizon execution and worker lanes. No further games are needed to reject these two frozen development variants.

## Contest product (titanmcp)

Live judge pad (≠ Commons Shared Pad / ≠ Commons `/mcp`): https://webmcp-pad.vercel.app/ — **titanmcp 1.4.5**, 24 tools, Agent Resources, `syncConsents`. Board: [titanmcp.html](../../../../titanmcp.html). Cite Latch Pad KEEP.
