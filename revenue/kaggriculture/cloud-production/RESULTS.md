# Development results

Candidate SHA-256: `0fbe51eea32be64a2441c60ba7867d532614812cbb9823bbc9087fb6aecdd7d5`

| Opponent | Games | Wins | Mean margin |
| --- | ---: | ---: | ---: |
| KAG-COMPOSE `dispatch_balanced`, seed 9200017 | 2 | 2 | +21,501.5 |
| Merged KAG-PRODUCTION, seeds 9200047/81 | 4 | 4 | +8,120.0 |
| Kaito v43, seed 9200017 | 2 | 0 | -22,541.5 |
| Igor MultiRoute, seed 9200017 | 2 | 0 | -21,259.0 |
| Kaito v43, seeds 9200047/81 | 4 | 0 | -21,415.5 |
| Igor MultiRoute, seeds 9200047/81 | 4 | 0 | -27,495.75 |
| Shipped KAG-PRODUCTION, seeds 9200131/157 | 4 | 2 | +5,315.75 |
| Kaito v43, seeds 9200131/157 | 4 | 0 | -36,309.5 |
| Igor MultiRoute, seeds 9200131/157 | 4 | 2 | -19,282.75 |

All 20 scheduled selected-policy games completed without agent failure. Each
report's first-game reproducibility replay matched terminal scores and trace.
Seeds `9200017`, `9200047`, and `9200081` are development-only. Kaito and Igor
are pinned public references, not the September 7, 2026 leaderboard leader.

The exact feed-before-seed correction was rejected at 0/2 and -14,139 mean
against the merged policy. The promoted policy instead books seeds first,
decrements their fixed cost, then prices each WHEAT fill sequentially while
preserving 30 cash. ROWAN's next-day refresh contract replaces the former
current-age fertilizer calculation: tomato events end at ages 8/9/10/11,
fertilizer targets only uncovered future refreshes, and late un-cashable crop
events are excluded.

The successor makes crop capacity responsive to current workers and observable
service load. Its separate labor-throttling arm lost 0/2 and -7,888 mean on
seed `9200131`, so those labor bytes were removed rather than bundled with the
winning crop-cap change. The crop arm's Kaito regression is retained above;
selection used paired checkpoint margin and the better worst strong-reference
gap, not a claim of universal improvement.

## Quarantined forecast/liquidation integration

SORREL's exact observation-only forecast from PR 9807 was integrated in two
bounded, transient arms on new seeds. Neither arm is promoted; the selected
`candidate.py` remains byte-exact at
`0fbe51eea32be64a2441c60ba7867d532614812cbb9823bbc9087fb6aecdd7d5`.

The forecast-price arm replaced the approximate crop quote and removed the old
shop-demand multiplier to avoid double counting. It averaged **+3,645.75**
against this checkpoint across seeds `9200191/9200229`, but its four-game mean
margin versus Kaito regressed from **-14,840.75** to **-20,626.75** and versus
Igor from **-16,491.0** to **-23,694.0**.

The partial-liquidation arm used exact sequential fills and sold appreciating
crop stock only to fund visible seed, feed, and Fibonacci labor commitments or
the configured shed-capacity requirement. It won 2/2 against the checkpoint on
seed `9200251` by **+1,683.5** mean, but regressed versus Kaito by **3,694** and
Igor by **20,878**. Against the newer Arlene/Apex panel on seed `9600109`, own
cash rose by 6,812/11,072, while opponent cash rose by 22,856/19,591; margins
therefore worsened by **16,044** and **8,519**. Holding supply helped the stronger
opponent more than it helped FLORA. No optimistic quote was treated as terminal
cash, and no forecast or liquidation bytes replaced the selected policy.

Normal full-game actor instrumentation also rejects per-action forecast calls:
the five treatment reports used 1,438–4,314 candidate calls each, with weighted
mean call CPU of **12.43–18.76 ms** and observed maxima of **99.01–928.68 ms**.
No forecast runtime bytes are promoted. A future use must cache by observation
and realization horizon rather than iterate every intermediate step on every
action.

Exact terminal scores and report hashes are in
`results/forecast-liquidation-rejected-development.json`.

## Contest product (titanmcp)

Live judge pad (≠ Commons Shared Pad / ≠ Commons `/mcp`): https://webmcp-pad.vercel.app/ — **titanmcp 1.4.5**, 24 tools, Agent Resources, `syncConsents`. Board: [titanmcp.html](../../../titanmcp.html). Cite Latch Pad KEEP.
