Latest continuation: [ROUTE-RESULTS.md](ROUTE-RESULTS.md), frozen carrot-demand reserved results and separate ordered-shed repair.

Current complete continuation: [NEXT-RESULTS.md](NEXT-RESULTS.md), 117 games and two next-candidate archives. The initial checkpoint below is retained for history.

# Frozen candidate generalization and isolated repair

The exact designated archive lost all 16 fresh development games: 8/8 losses to Arlene v14 (mean margin -21,472), 8/8 losses to Apex v1 (-22,334.25). All completed 719 rounds without runtime failures. This does not reopen the accepted reserved validation or alter the submission. Native loader initialization and process startup are measured separately in per-game.csv; raw games retain successful transaction units/cash, all ineffective-action events, daily full observations and terminal state in compressed JSON.

| Seed | Opponent | Frozen cash | Opponent cash | Margin |
|---|---|---:|---:|---:|
| 9500109 | Arlene | 95699 | 117284 | -17585 |
| 9500109 | Apex | 94896 | 108067 | -13171 |
| 9500123 | Arlene | 58389 | 80201 | -21812 |
| 9500123 | Apex | 56384 | 85385 | -29001 |
| 9500137 | Arlene | 110367 | 124822 | -14455 |
| 9500137 | Apex | 108338 | 127857 | -19519 |
| 9500151 | Arlene | 49495 | 81531 | -32036 |
| 9500151 | Apex | 49287 | 76933 | -27646 |

Each row occurred in both seats with the same cash for this initial panel. Later head-to-head games do show seat differences and different shop paths: final shop order is recorded separately for every game, not assumed seed-fixed.

The one-game service diagnostic repeated only the measured 9500109 Arlene loss to classify ineffective actions; its cash and trace match the initial result. A cow at (2,1), placed day 4, was unfed at steps 133 and 160 because the assigned workers held no wheat. It was absent at step 183, creating subsequent empty-pasture service turns. This is a concrete observation, not a claim that all the score gap comes from feeding.

Four matched games per isolated experiment (9500109, both opponents and seats):

| Change | Actual action/count result | Cash/margin delta vs frozen | Selection |
|---|---|---:|---|
| Feed during an ineffective service when worker already has wheat | Exact original traces; no opportunity | 0 | Reject as inactive |
| Prioritize feed over CARE | Three extra FEED, three fewer CARE per game | -5 | Reject |
| Harvest visible crop/animal yield during ineffective service or PASS | 61 extra HARVEST; action path changes propagate | -23381/-24452 own cash; -3258/-3244 margin | Reject |
| Restrict harvest rescue to animals | One FEED replaced by HARVEST; different trace | 0 | Reject as no cash gain |

The broad harvest failure shows why a ready-looking crop cannot be harvested early without its production schedule: ongoing care and the timing of destructive crop harvest matter. The bounded animal version harvests ready milk earlier, but the later parent harvest already recovers it; action productivity alone is not terminal cash improvement. These source files and raw failures are retained rather than promoted.

Production allocation is the larger next question. On 9500109, Arlene sold 261 milk and 350 fertilizer units versus frozen 239/246, with 45 ineffective actions versus 197. It supported 9 cows, 5 sheep and 3 geese at terminal versus frozen 10 cows/4 sheep/one empty pasture. These are measured outcomes in that market, not recommended inventory targets. Original traces include all source-player transactions for comparison.

Arlene then beat Apex in 8/8 fresh head-to-head games on 9500301, 9500319, 9500337 and 9500355. The first four margins were +9277, +112, +1827 and +2559; the next four +8453, +8453, +3719, +3719. Arlene is a stronger foundation on this sample, not a leaderboard-winning claim. Its existing milk-glut branch is chosen at step 433 although its route first diverges at 577. A separately named next experiment defers that same threshold decision to the common-prefix boundary, keeping every source route and inherited execution guard. Results for that experiment are pending in this checkpoint.

Reproduction: prepare.py, then build_experiment.py VARIANT --runtime DIRECTORY, then measure.py with the generated adapter and the recorded seeds. All policy builds/tests occurred in cloud; no credentials were retrieved, no notebook setup cells ran, and no paid compute or submission occurred. offline-guard.json confirms socket creation and subprocess execution were denied by the installed filter.

## Contest product (titanmcp)

Live judge pad (≠ Commons Shared Pad / ≠ Commons `/mcp`): https://webmcp-pad.vercel.app/ — **titanmcp 1.4.5**, 24 tools, Agent Resources, `syncConsents`. Board: [titanmcp.html](../../../../titanmcp.html). Cite Latch Pad KEEP.
