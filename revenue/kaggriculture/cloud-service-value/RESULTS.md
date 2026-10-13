# T04 results — September 7, 2026

## Outcome

The frozen v2 service treatment completed **32 full games**, 16 development and 16 held, against intact Arlene and Apex in both seats. Every game completed 719 official-interpreter decisions without an evaluator failure. The 20 engine and integration tests also passed.

Each panel contains eight paired comparisons: two seeds, two opponents and two seats, with an intact Arlene control and the service treatment run separately. The held policy and dependencies were frozen before either held seed ran. These are cloud simulations, not hosted Kaggle ratings.

| Panel | Control W/T/L | Service W/T/L | Tie-to-win changes | Mean additional own cash | Observed regressions |
| --- | --- | --- | --- | --- | --- |
| Development | 4/4/0 | 6/2/0 | 2 | 88.50 | 0 of 8 pairs |
| Held | 4/4/0 | 6/2/0 | 2 | 64.75 | 0 of 8 pairs |

All control wins were against Apex. Arlene control self-play tied. The treatment converted two Arlene ties to wins in each panel and retained all Apex wins. The two seat observations for a seed/opponent were symmetric; they are not independent environment samples.

## Paired cash and result detail

Each row below occurs in **both seats 0 and 1**, so it represents two paired cases. Cash is the official terminal money score. Positive margin delta means an improvement in own cash minus opponent cash, relative to the paired control.

| Panel | Seed | Opponent | Own cash delta per seat | Margin delta per seat | Control to service | Overrides per game |
| --- | --- | --- | --- | --- | --- | --- |
| Development | 9740001 | Arlene | 0 | 0 | Tie to tie | 0 |
| Development | 9740001 | Apex | 112 | 110 | Win to win | 1 |
| Development | 9740019 | Arlene | 119 | 118 | Tie to win | 1 |
| Development | 9740019 | Apex | 123 | 123 | Win to win | 1 |
| Held | 9740101 | Arlene | 130 | 131 | Tie to win | 1 |
| Held | 9740101 | Apex | 129 | 128 | Win to win | 1 |
| Held | 9740119 | Arlene | 0 | 0 | Tie to tie | 0 |
| Held | 9740119 | Apex | 0 | 0 | Win to win | 0 |

Every accepted override was the same observed mechanism: at decision592, hand1 at position `[4, 1]` harvested a full, already-fed goose rather than performing CARE. The animal held four units, had one pending care bonus and had been placed on day10. Harvesting freed held-output capacity before later production. No other present action differed from the intact parent on the same actual observation. Full difference snapshots and terminal state are in the raw reports.

The service treatment did not change the current capital, crop, hiring, movement or market orders, and left the final day untouched. It is not a complete new farm strategy.

## Runtime is a material cost

The treatment performs many conditional rollouts to accept very few overrides. It is substantially more expensive than the baseline, including in games where it accepts no change.

| Measurement | Development control | Development service | Held control | Held service |
| --- | --- | --- | --- | --- |
| Maximum measured candidate call, milliseconds | 37.03 | 661.06 | 10.73 | 534.79 |
| Mean candidate call CPU per game, seconds | 0.0410 | 5.5817 | 0.0374 | 3.7058 |
| Mean complete-game wall time, seconds | 4.1297 | 9.7386 | 4.0576 | 7.8512 |
| Maximum candidate process peak RSS, KiB | 106804 | 110644 | 107052 | 110892 |

The sampled maximum call remained below this evaluator's one-second decision deadline. That is a measurement on this cloud runtime, not a cross-machine guarantee. Full-game wall time includes both actors, driver and passive diagnostics. The existing evaluator's post-game forced actor cleanup can record exit code `-9`; the game completion, failure field and 719 successful decisions distinguish normal cleanup from an in-game failure.

## Preserved negative experiment

The first v1 experiment froze the parent's already-clamped future SELL quantities. It ran one paired case: development seed9740001, Arlene, seat0. Both arms scored 61,580 and tied, with no service override. That source, its freeze and both complete raw games are retained under `history/frozen-sells-v1/` inside the evidence archive.

The v2 change corrected that forecast assumption: retain the nominal worker/capital plan, but refresh future SELL quantities from the counterfactual shed. This change and the negative result were posted in the T04 thread before held evaluation. The v2 development rerun of the first case is not a new independent seed. No changes were made after inspecting held results.

## Evidence and scope

Run `python unpack_evidence.py --output evidence` from this directory. The resulting `results/development.json` and `results/held.json` contain all raw games, timing and resource data, traces, differences, terminal states, summaries and paired comparisons. `results/FREEZE.json` binds all four executed source files and exact dependencies. `test-run-3.log` records the final 20 passing tests. The archive and all 11 members were roundtrip verified against their originals, and the published chunks' Git blobs matched the local bytes.

Archive SHA256: `7035aca6ff94349c98168b0db69d059461c1ac2fa335550748f73e7625fd8f25`.

The evidence supports a narrow, reusable mechanism and a small held simulation benefit. It does not establish general win rate, population significance, dominance over a varied opponent league, compatibility with other overlays, or a hosted leaderboard improvement. There are only four unique environment seeds across v2. Future composition must consider the substantial computation cost and use new evaluation seeds. No Kaggle upload or current-policy promotion occurred.

## Contest product (titanmcp)

Live judge pad (≠ Commons Shared Pad / ≠ Commons `/mcp`): https://webmcp-pad.vercel.app/ — **titanmcp 1.4.5**, 24 tools, Agent Resources, `syncConsents`. Board: [titanmcp.html](../../../titanmcp.html). Cite Latch Pad KEEP.
