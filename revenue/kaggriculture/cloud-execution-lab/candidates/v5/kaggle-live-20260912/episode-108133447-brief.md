TITAN V4 won episode **108133447** in seat 1: **106,081 versus 84,786**, margin **+21,295**, both agents DONE. The downloaded submission snapshot binds seat 1 to submission **56182437**; opponent submission is 55577044, bhavya shah. Seed: 1120067126.

This is one actual Kaggle game, with candidate ideas rather than estimated rating gains. Decision step `t` uses replay observation row `t` and action row `t+1`. “From step 480” below means **480–718 inclusive**, zero-based day 20 onward.

Sales below are **filled quantities and realized gross sale receipts**, not requested amounts. The analysis applied the pinned official engine's unchanged unit-action and two-player market functions to each recorded input/action pair, counting only successful `_commit_unit` calls at the actual paired quote. All 719 money results matched the next recorded observation; every non-EOD shed result matched too. No candidate was called and no new or counterfactual game was run.

| Measure | Recorded result |
|---|---:|
| Lowest cash | $12 at steps 205–208 |
| Cash at steps 240 / 360 / 480 / 600 | $1,668 / $25,627 / $54,562 / $84,260 |
| Hires | 282 successful, $5,573 total, zero failed hires |
| Shed pressure | Maximum observed 99/100; 18 observations at least 90/100 |
| Shed overflow / terminal unsold goods | Zero recorded overflow loss; terminal shed and all carried inventory empty |
| Active actor actions | 7,127, including 523 explicit PASS |
| Unchanged non-PASS actions | 42: 17 WATER, 9 CARE, 8 PLACE, 5 HARVEST, 2 COLLECT_FERTILIZER, 1 PICKUP |
| Ignored extra actor rows | 22; mostly movement, plus 3 WATER and 5 PASS |

Three candidates fit existing lanes:

1. **State-dependent late livestock service — commons_swarm #1 herd/feed and worker valuation.** From step 480, 141 MILK sold for only **$1,408**, and 61 WOOL for **$77**. During the same period, 182 STRAWBERRY earned **$35,892**. There were still 133 effective FEED actions, 129 CARE actions and $2,896 of hiring expenditure across the whole farm. Candidate: compare each animal's next product **plus fertilizer** value against wheat and marginal labor, then reassign an existing worker's low-value service trip to useful crop work before considering fewer hires. Fertilizer still earned $2,677 during this period, so “stop every feed” is not justified. Exact late feed callbacks are in the brief JSON; the first are step 482 actors 0/8 and step 483 actors 4/9, continuing through step 669.

2. **Crash-responsive sale timing — commons_swarm #12 crash-dodge and #13 wool, existing TENON/HINGE work.** WOOL receipts deteriorated from 4 units/$135 at step 364 to 4/$35 at 367 and 6/$6 at 369. MILK's public quote fell from $135 at 432 to $74 at 456 and $1 at 504; 15 MILK remained in the shed at steps 432, 456, 480 and 504. Candidate: use visible supply, current town demand and rival standing yield to shorten hold targets when the market is deteriorating, allowing multiple products' sale decisions to change together. The later realized prices identify a failure mode; they must not become look-ahead information in the policy.

3. **Owned-input-aware purchase sizing — existing liquidity/procurement work.** At step 220, cash $126 plus a fertilizer receipt of $82 bought only 5 of 6 requested WHEAT for $175, leaving $33. WHEAT purchases at 222 and 224 then failed, while 24 WHEAT was already in the shed. Later, step 276 spent $240 for 6 WHEAT with 61 already stored; step 433 spent $172 for 4 FERTILIZER with 19 already stored. Candidate: size purchases from observed stock less the next actual feed/fertilize commitments, and protect useful near-term inputs through expansion shopping. These are concrete engagement points, not proof that every listed purchase loses money.

The empty terminal inventory and absence of overflow make generic endgame liquidation/overflow work a lower priority for this episode. Likewise, many PASS actions are deliberate waits for crops to mature; the count alone is not recoverable labor.

Detailed evidence: [brief JSON](episode-108133447-brief.json). Fetch full episode 108133447 using the official Kaggle SDK `get_episode_replay(ApiGetEpisodeReplayRequest)`; full replay state is retained by Kaggle and omitted from this compact dataset.
