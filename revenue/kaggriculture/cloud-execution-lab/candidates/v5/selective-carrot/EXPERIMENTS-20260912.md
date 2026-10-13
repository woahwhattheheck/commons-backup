# Production and route experiments — 2026-09-12

The existing production-v3 composition remains the research baseline. More permissive carrot valuation loses money in the measured active cells; later admission and higher profit thresholds have mixed results. On a separate PET_CAFE/BAKERY holdout, the default route 0 outperforms forced routes 1, 9, and 12. These findings support further portfolio research. No universal carrot threshold or route replacement is established.

All 35 games use the exact baseline archive `20f201161b14af7755146b08207593f9fa5df641d2f31e680792ea62c0e24239` or a treatment derived from it, the pinned official engine, responsive Arlene_v14, seat 0, and explicit observation steps. Local timer guards were disabled. Every game completed 719 decisions without fallback. These development results do not establish native timing or hosted rating. No treatment is promoted, gameplay defaults and release pointers are unchanged, and Kaggle submission remains held.

[EXPERIMENTS-20260912.json](EXPERIMENTS-20260912.json) retains absolute scores, action hashes, original-report hashes, source transformations and postimage hashes, crop engagement, and the cash ledger. Each treatment changes one member of the 92-member baseline. Source postimages were captured from the materialized experiments; raw reports directly retain their main.py hash. The JSON distinguishes these evidence sources.

## Crop admission

Cells show margin change against their same-seed baseline; dashes were not tested.

|Treatment|1209125501|1209125503|1209129901|1209132201|
|---|---:|---:|---:|---:|
|R04 checkpoints 144/648|0|0|0|—|
|Checkpoints + admission from 144|0|0|0|—|
|Checkpoints + age 2 harvest eligibility|0|0|0|—|
|Receipt factor 0.95, from 0.8|−271|−41|0|—|
|Receipt factor 1.0|−499|−77|0|—|
|Disable carrot choice|−847|−558|0|—|
|Admit only from 528, from 240|+301|−8|0|—|
|Required margin 24, from 12|+322|−206|—|0|
|Required margin 32|+121|−418|—|0|

The checkpoint, early, and age2 variants return the exact baseline action streams in these cells. Their effects outside these cells remain unmeasured. Baseline crop choice plants 13/12/0 replacement lots on seeds ending 5501/5503/9901. Removing choice loses relative score in both active cells. Raising the receipt factor admits more marginal projects and loses in both active cells; retain those variants as negative research results. Thresholds 24/32 and admission at 528 trade gains on 5501 for losses on 5503, so none is promoted globally.

The exact engine cash replay explains `value95` on 5501. It reproduces all 30 retained state checkpoints for each arm, including farms, private game inventory, market and town:

|Own realized change|Cash delta|
|---|---:|
|30 additional CARROT sold|+682|
|30 additional WHEAT purchased|−1286|
|CARROT seed expense|−200|
|WHEAT seed saving|+90|
|Same 307 WHEAT sold at changed prices|+181|
|Total own cash|**−533**|

CARROT harvest rises 144→174 while WHEAT harvest falls 480→450. Rival quantities are unchanged; rival CARROT revenue falls 505 and WHEAT revenue rises 243, totaling −262. Thus relative margin changes −533−(−262)=**−271**, exactly matching the paired game. Extra crop receipts do not cover replacement feed cost in this cell.

## Route holdout and compatibility

Seed 1209132201 reveals PET_CAFE/BAKERY at step 144. Each forced arm changes only the step 144 selection; all retain the installed switch to route 2 at 648.

|Selection|Own cash|Rival cash|Margin|Delta versus baseline|
|---|---:|---:|---:|---:|
|Default / forced R00|69875|55556|14319|0|
|Forced R01|62475|66330|−3855|−18174|
|Forced R09|57407|63315|−5908|−20227|
|Forced R12|53101|47983|5118|−9201|

Default and forced R00 have identical action hashes. This single holdout does not rank routes across shop regimes.

[ROUTE-DESIGN-20260912.json](ROUTE-DESIGN-20260912.json) records all 13 tapes, their configured shop pairs, opening compatibility and requested supply. Twelve tapes have identical steps 0–143. R01 differs by three omitted CAREs, one omitted WATER, and six fertilizer-sale rows; its movement and fixed purchase/custody operations are identical. Two retained exact-baseline starts have the farmer at (4,4), no temporary hands, empty carried inventory/seeds, shed stock of 16 WHEAT+2 FERTILIZER, four COW and two SHEEP, and cash of 800/798. All 26 immediate route/start checks pass; later affordability remains market-dependent.

The following counts describe **authored requests from 144–647**; they do not measure realized production. Added animals exclude the shared opening herd. Crop columns are WHEAT/CARROT/STRAWBERRY; no TOMATO/MELON planting is requested in this interval.

|Route|Added COW/SHEEP/GOOSE|PLANT requests|FEED requests|WHEAT buys|
|---|---:|---:|---:|---:|
|R00/R02|4/4/3|138/29/29|317|110|
|R01|2/8/0|138/29/29|317|66|
|R03|2/9/0|138/29/29|317|109|
|R04|2/8/0|138/29/29|317|87|
|R05|2/8/0|138/29/29|317|75|
|R06/R07/R08/R11|2/9/0|138/29/29|317|84|
|R09|2/9/0|140/26/29|326|128|
|R10|2/9/0|138/29/29|317|112|
|R12|0/12/0|140/26/29|311|113|

R09 starts with five hires costing 12; others use seven costing 33. R09/R12 buy two SHEEP during day 6 where the other tapes buy two COW. R01/R05 share the same middle-period worker commands but different market schedules. An adaptive selector therefore needs to distinguish production portfolio from provisioning and selling timing. Existing R04 and V4 processing layers remain part of every measured candidate.

Packaging checks reconciled all 35 score/action summaries with their retained reports, recomputed every margin delta, matched all 92 baseline archive members, confirmed one changed member per treatment, and closed both ledger cash deltas. This publication adds the evidence files without introducing new simulations or another experiment harness.
