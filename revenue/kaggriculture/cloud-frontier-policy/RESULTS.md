# Selected policy results

Frozen policy SHA-256: `b3a6085e1e6674f0228fca4b31fe90950875c1ef93c8c8d926dbc586298c0b56` (73,212 bytes). Native-loader main.py is that exact byte prefix plus a new uniquely named delegating entrypoint, SHA-256 `16d7f213e06c563487e5f613f8c94116a094b36ba46927329cbfc3b4195d461d` (73,418 bytes). No policy parameters changed after selection.

| Phase | Opponent | W/T/L | Mean own cash | Mean opponent cash | Mean margin |
|---|---|---|---:|---:|---:|
| Development | kaito_v43 | 8/0/0 | 88,690.875 | 84,203.375 | +4,487.500 |
| Development | igor_multiroute | 8/0/0 | 81,591.750 | 70,015.250 | +11,576.500 |
| Reserved validation | igor_multiroute | 8/0/0 | 84,001.750 | 71,784.875 | +12,216.875 |
| Reserved validation | kaito_v43 | 8/0/0 | 91,153.375 | 83,624.875 | +7,528.500 |

The selected variant won all16 development and all16 reserved games, both seats against both source parents. Four validation seeds were reserved before selection (selection.json; Slack freeze1788772606.334099). They were run once each against each parent in both seats, without parameter retuning. Pairings share seeds and are not16 independent environments. This is evidence for root's submission selection, not a measured leaderboard rating or proof against the current leader.

## Reserved per-game results

Wall time includes passive driver diagnostics; decision maximum is measured inside the isolated agent process. Raw JSON includes every daily cash snapshot, actual market units/proceeds, action/no-op counts and final private inventory. CSV includes all timing/action fields.

| Opponent | Seed | Seat | Own cash | Rival cash | Margin | Wall s | Max call ms | Non-PASS unchanged |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| kaito_v43 | 9400203 | 0 | 129,283 | 117,125 | +12,158 | 5.418 | 2.237 | 63 |
| kaito_v43 | 9400203 | 1 | 129,283 | 117,125 | +12,158 | 5.393 | 2.358 | 63 |
| igor_multiroute | 9400203 | 0 | 65,423 | 53,326 | +12,097 | 6.507 | 10.418 | 31 |
| igor_multiroute | 9400203 | 1 | 75,905 | 62,236 | +13,669 | 7.292 | 6.570 | 31 |
| kaito_v43 | 9400217 | 0 | 75,123 | 71,609 | +3,514 | 6.950 | 6.277 | 65 |
| kaito_v43 | 9400217 | 1 | 71,106 | 67,476 | +3,630 | 6.693 | 5.366 | 66 |
| igor_multiroute | 9400217 | 0 | 58,838 | 49,156 | +9,682 | 6.115 | 3.371 | 31 |
| igor_multiroute | 9400217 | 1 | 58,774 | 49,145 | +9,629 | 5.855 | 5.036 | 31 |
| kaito_v43 | 9400231 | 0 | 54,158 | 50,445 | +3,713 | 5.858 | 3.542 | 63 |
| kaito_v43 | 9400231 | 1 | 54,158 | 50,445 | +3,713 | 6.016 | 8.613 | 63 |
| igor_multiroute | 9400231 | 0 | 83,897 | 70,133 | +13,764 | 5.211 | 2.015 | 31 |
| igor_multiroute | 9400231 | 1 | 89,735 | 75,361 | +14,374 | 5.248 | 2.665 | 31 |
| kaito_v43 | 9400249 | 0 | 108,058 | 97,387 | +10,671 | 6.155 | 4.874 | 66 |
| kaito_v43 | 9400249 | 1 | 108,058 | 97,387 | +10,671 | 7.669 | 5.245 | 66 |
| igor_multiroute | 9400249 | 0 | 119,721 | 107,461 | +12,260 | 8.014 | 7.219 | 30 |
| igor_multiroute | 9400249 | 1 | 119,721 | 107,461 | +12,260 | 8.768 | 11.869 | 30 |

## Native loader and exporter

Accepted cloud-pack exporter produced export/submission.tar.gz (57711 bytes), SHA-256 `79b407d699b5fd39e7b396de8b6fc79b2bc2fb99f427f7e2e7ecd25fbc71fb0b`, with main.py, Apache LICENSE, attribution NOTICE.txt and PACK-MANIFEST.json. An initial failed archive is not shipped: its first call selected a helper because redefining an earlier entrypoint does not move its dictionary insertion position. results/native-first-failed.json preserves that discovery. main.py fixes only loader selection by appending a new unique function name; candidate.py remains the frozen validated policy.

Corrected exported cold calls took 284.242/138.255 ms including lazy loader/source initialization; fresh process through first response took 565.416/229.564 ms. Both initial actions exactly matched direct source. Four complete source/export games on development seed9400109 (both seats vs Kaito) matched cash and action-trace hashes, each719 rounds. Exported cash100306 versus98328 in both seats. Full report results/native-loader.json pins exporter, evaluator and loader sources. These are cloud native Python/pinned official file-loader measurements, not an actual hosted Kaggle sandbox certification. No accepted PR9770 orientation tests were rerun; this new candidate required its own native check.

## Experiments and interpretation

There were76 development/control games,16 reserved validation games and4 new-candidate source/export complete games:96 total full games. All completed. Rejected policies lost; those losses were not hidden. Three focused market-slot regressions pass. CHECKPOINT2.md and each raw report retain the actual-parent / route-only / sales-only ablations.

The first reconstruction combined multiple edits and truncated hire orders. Its eight losses did not identify route switching as causal. Route-only Igor control matched actual Igor exactly; a slot-preserving sale edit gave only+121 against Igor and still lost to Kaito. The selected implementation calls Kaito's ACTUAL entrypoint once and changes no worker action, route selector, seed/feed/capital order or parent state progression. For visible farm-signature distance<=2 it adjusts finished-product quantities and adds sales only in free slots; otherwise it returns the parent action. It uses existing public state only, no opponent private inventory or environment seed. The gate improved development cash versus unconditional sales while retaining wins; this is not a universal immediate-sale claim.

Winning margin is the competition objective. On one control seed earlier sales lowered both players' cash but improved margin, so the edit was not rejected solely for lower own cash. ROWAN's leader replay contextualized productive scheduling and endogenous sale prices; no one-game crop counts were copied into this policy. Submission/account transport remains with root/ROWAN.

## Contest product (titanmcp)

Live judge pad (≠ Commons Shared Pad / ≠ Commons `/mcp`): https://webmcp-pad.vercel.app/ — **titanmcp 1.4.5**, 24 tools, Agent Resources, `syncConsents`. Board: [titanmcp.html](../../../titanmcp.html). Cite Latch Pad KEEP.
