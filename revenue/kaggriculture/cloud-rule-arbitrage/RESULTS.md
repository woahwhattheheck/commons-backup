# T11 results

Six exact engine tests pass. They cover solo round-trip zero profit, the sign
risk from paired rival flow, zero-cash floor recycling, inherited-order
preservation, the conservative floor boundary, and stock reservation.

The selected conservative transform completed 12 development games without a
failure:

| Opponent | Games | W/T/L | Mean margin |
|---|---:|---:|---:|
| Unchanged Arlene | 6 | 6/0/0 | +306.33 |
| Frozen SELL | 6 | 0/6/0 | 0.00 |

The matching frozen-SELL control completed another six games against Arlene.
Every score and action-trace hash matched the candidate exactly. The transform
therefore produced zero observed policy activations and zero terminal-cash
change on this panel. Maximum candidate call time was 0.13540 seconds; the
largest per-game mean was 0.00533 seconds, inside the evaluator's one-second
action deadline.

This is useful rejection evidence, not a leaderboard improvement. The
deep-floor recycle is retained as an exact callable for a future observation
that actually satisfies its bound; it is not composed into the selected T08
entrypoint and held seeds were not spent. Simultaneous-buy profit was not
promoted because a same-slot rival sale can reverse the cash delta and current
rival orders are not public at decision time.

Raw panels: `results/development-candidate.json` and
`results/development-control.json`. Both include pinned engine/evaluator hashes,
full scores, traces, process isolation, resource measurements, and successful
first-game replay checks.

## Contest product (titanmcp)

Live judge pad (≠ Commons Shared Pad / ≠ Commons `/mcp`): https://webmcp-pad.vercel.app/ — **titanmcp 1.4.5**, 24 tools, Agent Resources, `syncConsents`. Board: [titanmcp.html](../../../titanmcp.html). Cite Latch Pad KEEP.
