# Continuity result

The `401d2dbc` current package is action- and economy-continuous with the retained
`70554dc0` ancestor on seed `9922023`, both seats.

| Candidate seat | Current terminal cash | Retained ancestor | Full trace SHA-256 | Divergence |
|---:|---:|---:|---|---:|
| 0 | 56,735 vs 55,859 | 56,735 vs 55,859 | `5930054e8b8ac66fb596e48bebbca2fd2471d3e0e66debed6f1e6f1345d18a0b` | 0 |
| 1 | 56,109 vs 56,495 | 56,109 vs 56,495 | `3d68450e97a956e3b258af71ded86ca66d46bbf0bac9af0877c0a040c886c5e3` | 0 |

Both current trace digests exactly match PR10156's retained evaluator rows. Thus
there are zero changed action/bank/final-state records across the two complete
719-round games. The retained +$240 seat-0 gain and +$250 disadvantaged-seat gain
remain exact; the latter still does not erase the inherent seat disadvantage and
therefore remains the one loss. Direct comparison against the retained seat-1
full trace also finds zero action-round and zero bank-transition differences.

The current production entry reaches funding at step 600 and invokes the hook
exactly once. It transforms `BUY_SEED WHEAT 17` to `BUY_SEED WHEAT 1`, preserves
all seven following HIRE orders, records a certified $160 current-market cash
reduction, makes no extra controller call and uses no rival-private state. The
entrypoint prelude was 63.5 µs; the whole reached call was 10.93 ms wall / 10.85 ms
CPU. This is the actual shipped config (`funding=true`, history/terminal off), not
a test-only feature overlay.

Current consumer timing under the real one-second RPC boundary:

| Seat | Worker source load | First action child / RPC | Maximum child / RPC | Mean child / RPC |
|---:|---:|---:|---:|---:|
| 0 | 130.54 ms | 69.48 / 71.73 ms | 259.04 / 287.14 ms | 5.98 / 7.70 ms |
| 1 | 683.29 ms | 107.90 / 109.10 ms | 130.17 / 130.90 ms | 3.63 / 4.70 ms |

Both games completed with zero external timeout, crash, invalid action or engine
error. Worker source-load timing is separate from the first lazy policy action;
the seat-1 startup outlier is reported rather than generalized. Internal deadline
fallback count is not asserted because the unchanged evaluator entry protocol
does not export per-call diagnostics. No timing is extrapolated into a broader
performance or strength claim.

## Contest product (titanmcp)

Live judge pad (≠ Commons Shared Pad / ≠ Commons `/mcp`): https://webmcp-pad.vercel.app/ — **titanmcp 1.4.5**, 24 tools, Agent Resources, `syncConsents`. Board: [titanmcp.html](../../../../titanmcp.html). Cite Latch Pad KEEP.
