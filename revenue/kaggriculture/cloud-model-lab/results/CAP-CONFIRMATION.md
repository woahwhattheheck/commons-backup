# Cap-overflow harvest: frozen confirmation on seeds 9700201-9700206

Candidate source frozen before any of these seeds were run, and byte-identical to
the freeze record throughout:

    arlene_plan.py  68a7f53710f12ab51330411a12d7c849dba62e6be8add14c07b592b8d7f302d5
    run_cards.py    878de644684b9a2631f709687570264f3081b34ef4d445f01a11f602f95a3a51

Seeds 9700201-9700206 appeared in no prior record, result file or run log of this
lane before execution. Both seats, versus intact Arlene and versus Apex, paired
candidate against control, single process. Nothing was tuned on these seeds.

## Rating-relevant result

| | control | candidate |
|---|---|---|
| pairs | 24 | 24 |
| **W/T/L** | **12/12/0** | **18/6/0** |
| per-pair flips | | **6, every one T → W** |
| pairs where own cash or margin got worse | | **0** |

Per-pair flips:

| seed | seat | opponent | flip | margin |
|---|---:|---|---|---|
| 9700203 | 0 | Arlene | T → W | +0 → +14 |
| 9700203 | 1 | Arlene | T → W | +0 → +14 |
| 9700205 | 0 | Arlene | T → W | +0 → +142 |
| 9700205 | 1 | Arlene | T → W | +0 → +142 |
| 9700206 | 0 | Arlene | T → W | +0 → +108 |
| 9700206 | 1 | Arlene | T → W | +0 → +108 |

Diagnostics, not the rating: mean d_own +47.2, mean d_margin +46.6. Eight of the
24 pairs recorded zero fills -- no reachable animal was about to overflow, so the
candidate did nothing at all rather than perturb a game it has no thesis about.
Every candidate shares an identical end-of-day RNG path with its control across
all 30 days, in all 24 pairs, so none of this is a different town.

## All three panels

| panel | pairs | control | candidate | flips | own cash or margin worse |
|---|---:|---|---|---|---:|
| development 9600011/9600029 | 8 | 4/4/0 | 6/2/0 | 2, both T→W | 0 |
| reserved 9700037/9700053 | 8 | 4/2/2 | 6/0/2 | 2, both T→W | 0 |
| **confirmation 9700201-9700206** | **24** | **12/12/0** | **18/6/0** | **6, all T→W** | **0** |
| total | 40 | | | **10, all T→W** | **0** |

This is a candidate, not a leaderboard improvement: forty paired games against two
local opponents under a pinned interpreter say nothing about hosted rating. No
win or tie has become a loss in any of the forty, and every flip runs the same
direction.

## Not tuned

One plan in five completes, so the candidate captures well under the output the
cap destroys (42 units, about $1,732, on seed 9600011 alone). Raising that is a
new candidate needing new development seeds. These confirmation seeds are spent.

## Contest product (titanmcp)

Live judge pad (≠ Commons Shared Pad / ≠ Commons `/mcp`): https://webmcp-pad.vercel.app/ — **titanmcp 1.4.5**, 24 tools, Agent Resources, `syncConsents`. Board: [titanmcp.html](../../../../titanmcp.html). Cite Latch Pad KEEP.
