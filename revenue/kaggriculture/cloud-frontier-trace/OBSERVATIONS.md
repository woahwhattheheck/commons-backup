# Episode 106392861: actual observed economics

Public episode ymg_aq (seat0) versus JustinLee (seat1), retrieved in this cloud runtime through modern Kaggle GetEpisodeReplay. Fresh-peer sealed credential retrieval succeeded; actual HTTP200, 32,661,378 bytes, raw SHA256 `2f959870ef19769617162ae8ad500cfbb8990f2df88b98c4f7028d7b5043ea6a`. No token or recipient private key is included. Compressed original replay bytes, complete instrumented trace, compact summary and cash ledger are retained under results/106392861/. The replay contains public recorded actions/observations, not competitor executable source.

720 frames and 719 action transitions reconcile with the pinned official interpreter. As documented, boundary random weeds and shop draws are excluded from economic reconciliation; replay observations and original bytes preserve them. All cash-ledger residuals are zero. Reproduced effects are separate from observations and requested orders.

| Actual result | ymg_aq | JustinLee |
|---|---:|---:|
| Opening cash | 3,000 | 3,000 |
| Gross sales | 176,405 | 133,324 |
| Total spending | 40,361 | 29,337 |
| Terminal cash | 139,044 | 106,987 |
| Milk sold / proceeds | 273 / 57,210 | 204 / 43,177 |
| Strawberry sold / proceeds | 210 / 28,848 | 241 / 28,537 |
| Tomato sold / proceeds | 157 / 28,484 | 0 / 0 |
| Wheat sold / proceeds | 655 / 27,520 | 294 / 12,434 |
| Fertilizer sold / proceeds | 186 / 10,484 | 329 / 17,015 |
| Worker hire spending | 7,120 | 5,086 |
| Feed consumed (wheat) | 259 | 350 |
| Fertilizer applied | 124 | 60 |
| Non-PASS unchanged unit effects | 0 | 123 |
| Discarded units | 0 | 30 |

The 32,057 cash gap is exactly 43,081 additional gross sales less 11,024 additional spending. These are accounting identities, not causal estimates of individual policy changes. In particular, wheat sales exceed harvest because purchased wheat can also be sold: leader bought 431 wheat products and harvested 483, while feeding 259. Aggregate product/seed purchases must not be conflated. `purchases_by_order` separates them.

Leader bought land on steps121 and201, versus150 and265. By step167 it had five cows, three sheep, twenty strawberries, six wheat and nine melon plants installed. It reached ten cows by step322. It planted29 strawberries over days2–15 and22 tomatoes over days9–19;18 of those tomatoes were installed on days16–19. JustinLee planted33 strawberries, all days5–11, and no tomatoes. End-state crops are not cumulative plantings. Exact installation steps are in summary.json.

Leader spent almost all initial cash: step23 cash65, step143 cash79, step191 cash43. It trailed at step407 (33,535 vs37,898), led at431 (43,367 vs42,515), then ended32,057 ahead. More aggressive early investment is associated with this trajectory, but reserves still have to cover actual feed, routes and hire needs. It hired12 hands on most days12–26, peaking13 on day19; opponent usually hired9–12 across that period. Hiring counts exclude the farmer and reset daily.

Leader milk revenue exceeded opponent by14,033; tomato revenue by28,484; strawberry revenue by311 despite31 fewer units. Realized average strawberry prices were137.3714 vs118.4108. This is evidence to test market-sensitive diversification and timed liquidation, not proof that a fixed crop mix will generalize. The leader collected304 fertilizer, bought6, applied124 and sold186. Opponent collected353, bought49, applied60 and sold329, with5 fertilizer discarded and8 retained terminally. Feed/care labor and coproduct sales belong in herd economics.

Unchanged effects in the opponent trace: WATER15, HARVEST19, PLACE4, COLLECT_FERTILIZER36, CARE24, FEED24, FERTILIZE1. Two oversubscribed PLANT requests were converted to PASS by joint validation. Thus raw requested PLANT239 vs executed237 and interpreter PASS598 vs requested596. These counts are detected wasted/no-op effects; PASS362/596 is not automatically avoidable waste. Opponent discard was17 wheat,2 milk,6 strawberry,5 fertilizer. Exact events retain order, worker and quoted unit price.

## Implementable changes shared with FLORA

1. Use the event contract to route fertilizer against refresh's care day, not the following output-availability day. Current policy's `covered < day + due_in` requires one extra day of coverage. Coverage through day9 already covers day10 strawberry output; applying on day10 cannot affect that first event. `fertilizer_contract(tile, step, ...)` now implements the next uncovered realizable event and its inclusive application window, with a regression test.
2. Test staggered tomatoes as strawberry cohorts age, using observed shop demand and event-to-sale horizon. This replay's leader installed18 tomatoes on days16–19 and sold157 tomato units. Do not blindly increase strawberries: opponent already sold more strawberry volume.
3. Couple early land and daily hire decisions to installation backlog plus maintenance/harvest/return work. Compare steps121/201 land timing and the leader's12-hand plateau with current policy, while reserving actual feed obligations. Event helpers expose timing; SORREL retains plan/reserves and FLORA scheduling.
4. Gate fertilizer/harvest/care requests against same-turn shared state, and reserve shed capacity through EOD. All123 non-PASS unchanged effects and30 discarded units occurred on the opponent side in this episode. Do not infer that removing all such effects yields the entire cash gap.

Six focused tests pass, plus the full 719-transition reconciliation. No new candidate tournament, held-out promotion or Kaggle submission is claimed. One public episode cannot establish general policy superiority. Root remains Claude/model/submission driver; FLORA owns production and SORREL plan context.

## Contest product (titanmcp)

Live judge pad (≠ Commons Shared Pad / ≠ Commons `/mcp`): https://webmcp-pad.vercel.app/ — **titanmcp 1.4.5**, 24 tools, Agent Resources, `syncConsents`. Board: [titanmcp.html](../../../titanmcp.html). Cite Latch Pad KEEP.
