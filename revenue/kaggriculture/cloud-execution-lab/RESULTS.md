# T08 results: frozen finite-horizon v3

**Development: 12W/0T/0L. Held-out: 8W/0T/0L.** The paired unchanged-Arlene controls recorded 6W/6T/0L and 5W/2T/1L. All figures describe local full games run inside this session's cloud container with the pinned official interpreter and existing process-isolated evaluator. They are not hosted Kaggle rating results or a submission designation.

## Panels and paired outcomes

| Panel | Policy | W | T | L | Games | Maximum action including cold start |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| Development | Selected v3 | 12 | 0 | 0 | 12 | 0.203147 s |
| Development | Unchanged Arlene | 6 | 6 | 0 | 12 | 0.181473 s |
| Development | Frozen v1 six-unit batch control | 4 | 0 | 8 | 12 | 0.180514 s |
| Held-out | Selected v3 | 8 | 0 | 0 | 8 | 0.188916 s |
| Held-out | Unchanged Arlene | 5 | 2 | 1 | 8 | 0.213077 s |

Development seeds were 9600803, 9600821, and 9600839; each policy played both seats against unchanged Arlene and Apex. The held-out seeds were 9600901 and 9600919, again both seats against both opponents. Candidate source was frozen before either held-out seed was used. No LARK evaluation seed from 9700101 through 9700112 was used.

The selected v3 produced six T→W flips in development. Held-out produced two T→W flips and one L→W flip; the five other baseline W outcomes remained W. There were zero reverse outcome flips for v3 in these panels. The frozen naive control produced six T→L and two W→L flips in development. W/T/L is primary because the game rates the outcome rather than the size of the cash margin.

The final development comparison contains 36 games, including 24 reused unchanged-baseline and frozen-naive controls. The v1 and v2 candidate iterations add 24 historical development games. Together with 16 held-out games, this gives **76 unique competitive games: 60 development and 16 held-out**. The separate complete-game terminal-window mechanics probe is not counted as a competitive game or candidate win.

## Held-out final cash by seat

Each row pairs the same seed, opponent, and candidate seat. “Own / rival” consistently refers to the tested policy's perspective, not absolute engine seat order. Amounts are in game dollars.

| Seed | Opponent | Seat | Baseline W/T/L | Baseline own / rival cash | v3 W/T/L | v3 own / rival cash |
| --- | --- | --- | --- | --- | --- | --- |
| 9600901 | Arlene | 0 | T | 98,762 / 98,762 | W | 99,240 / 99,163 |
| 9600901 | Arlene | 1 | T | 98,762 / 98,762 | W | 99,240 / 99,163 |
| 9600901 | Apex | 0 | W | 96,924 / 89,837 | W | 97,379 / 89,282 |
| 9600901 | Apex | 1 | W | 96,924 / 89,837 | W | 97,379 / 89,282 |
| 9600919 | Arlene | 0 | L | 84,826 / 84,907 | W | 85,023 / 84,461 |
| 9600919 | Arlene | 1 | W | 84,907 / 84,826 | W | 85,104 / 84,380 |
| 9600919 | Apex | 0 | W | 85,139 / 81,511 | W | 84,108 / 81,180 |
| 9600919 | Apex | 1 | W | 111,482 / 101,968 | W | 111,570 / 102,836 |

## Actual sale receipts and timing

The passive engine transaction hooks record accepted per-unit prices and quantities, including floor-price receipts. These are actual SELL proceeds before operating expenditures, not simulated optimizer scores or final cash.

| Panel | Policy | Actual SELL units | Actual SELL receipts |
| --- | --- | ---: | ---: |
| Development | Selected v3 | 18,400 | 1,485,228 |
| Development | Unchanged Arlene | 18,400 | 1,486,402 |
| Development | Frozen v1 six-unit batch control | 18,400 | 1,467,684 |
| Held-out | Selected v3 | 12,178 | 971,442 |
| Held-out | Unchanged Arlene | 12,178 | 970,125 |

Own receipts alone do not determine the match outcome: selected development receipts are 1,174 below the baseline total while its W count is higher. Individual own-cash and rival-cash changes, exact transaction totals by product, actual per-unit trace receipts, and paired outcomes are preserved in the linked JSON reports and their trace references.

Across the selected 20 games, maximum measured action time including the cold comparison was **0.203147334 s**, maximum process-start-plus-first-call time was **0.191231508 s**, and longest complete episode was **8.538961411 s**. The 0.291 s observation belongs to the earlier v2 research variant and is not the selected v3 maximum. Actor startup, imports, and initialization are included in the recorded cold/episode accounting. Every selected action completed within the one-second allowance.

A separate unchanged-parent replay consumed the candidate's exact observation sequence after each game, solely for preservation inspection. All **14,380 actions** retained farmer and hand actions plus non-SELL order values and original indices. Every selected game reached decision 718; selected terminal shed and carried-stock totals were zero. These observation replays are analysis only and never enter the runtime policy.

## Development trace and revisions

The frozen naive control supplies an actual counterexample to indiscriminate batching. On seed 9600803, seat 0 against unchanged Arlene, baseline finished T at 110,538 / 110,538 cash. The naive control finished L at 108,888 / 111,643. Both sold 72 MELON, but the baseline received 14,267 and the naive control received 13,253.

At decision 250 the naive control offered six MELON while its opponent offered 24, followed by 12 at decision 251. None of the currently unlocked shops consumed MELON. The delayed remaining tranches encountered that actual supply path. The finite-horizon v1 candidate retained the baseline MELON tranches in this window. This explains the observed comparison; it does not assert that delay always produces L. Future rival actions are present only in the post-game [trace analysis](runtime/v1-naive-loss-analysis.json).

V1 and v2 remain research snapshots rather than the selected callable. V2 extended delayed-rival scenarios, made short-horizon continuation valuation undiscounted, considered all available saleable products, added capacity-restoring choices and order-slot feasibility, and preserved duplicate/withheld SELL positions so later operating orders keep their indices. V3 then accumulated the successive BUY_LAND costs in the operating-cash projection. [SOURCE-FREEZE.json](SOURCE-FREEZE.json) records that final source before held-out play; the raw selected source remained unchanged afterward.

The semantic work contains 11 engine test cases, including the separate real-runner final-window probe and 945 exact runtime/official quote comparisons. It distinguishes price-floor admission, simultaneous precommit quotes, known town absorption, rival supply before a later batch, shared stock between two orders, cash-dependent order positions, DROP/EOD overflow, and final decision 718. [test_scheduler.py](test_scheduler.py) adds 12 focused scheduler cases covering relative scenario value, short-horizon carry, post-unit stock, cash/capacity reservations, ordered SELL positions, and terminal settlement. Details and source hashes are in [ENGINE-SEMANTICS.md](ENGINE-SEMANTICS.md).

## Interpretation and source record

This is a small paired panel over two public opponents. Public observed-yield rival scenarios are conditional stress cases, not calibrated probabilities or a private-stock estimate. Capacity forecasts follow only the current own route, without hidden RNG, unknown new shops, or future replay inputs. The optimizer chooses worst-scenario relative improvements within its finite tranche family; it does not solve a global game optimum or directly predict rating. A preserved W can have either sign of own-cash change, as the held-out seat rows show.

The planning mechanism is attributed to [Boyd et al., section 5](https://web.stanford.edu/~boyd/papers/pdf/cvx_portfolio.pdf) and [Cvxportfolio MultiPeriodOptimization](https://www.cvxportfolio.com/en/stable/optimization_policies.html): plan several decisions, execute the first, and replan. This implementation uses the game's discrete transitions; no GPL implementation code was copied. Engine, evaluator, Arlene, and Apex attribution remains attached to the retained sources.

| Artifact | SHA-256 |
| --- | --- |
| Selected scheduler.py | `32c8610c9827d1686a6f831e2c4b6af4c00d32d2aa04dcf25699d976d6d97dd9` |
| SOURCE-FREEZE.json | `37ffcba618a4a640ceae08b54a1770569904cc29b2698eb6377a7b3aa62eb283` |
| [Development paired report](runtime/development-v3-paired.json) | `19cbdf764d7f95a902ccc5799c99b1291591fecde09dfcbf4b61277b15155b6b` |
| [Held-out report](runtime/heldout-v3.json) | `b903365f7ce4cf61580c4ae0de7001f640534a338238fdb5383a2bde9aa3ab77` |

[FINAL-EVALUATION-SUMMARY.json](runtime/FINAL-EVALUATION-SUMMARY.json) collects the selected source, W/T/L, paired flips, timings, terminal state, and these report hashes. The callable interface and composition boundaries are documented in [README.md](README.md). This lane performed no Kaggle submissions, public-notebook writes, paid-service work, or real financial trades.

## Contest product (titanmcp)

Live judge pad (≠ Commons Shared Pad / ≠ Commons `/mcp`): https://webmcp-pad.vercel.app/ — **titanmcp 1.4.5**, 24 tools, Agent Resources, `syncConsents`. Board: [titanmcp.html](../../../titanmcp.html). Cite Latch Pad KEEP.
