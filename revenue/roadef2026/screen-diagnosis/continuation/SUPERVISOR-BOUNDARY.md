# Current portfolio boundary consumed by the reconciliation

Exact source read: `revenue/roadef2026/fleet-candidate/supervisor.py`, Git blob
`6a32f242aeaa85da70942e39aa1ea2a3c781d383`.

`Supervisor.start_lanes()` constructs one base environment, removes
`SEDGE_STATS`, `SEDGE_MAX_ROUNDS`, and `CLOUD_INITIAL_SOLUTION`, then launches
`sedge`, `flora`, and `candidate` independently against the original inputs and
separate output paths. No lane is restarted from a validated solution produced by
another lane.

This is why LANDING's saved-incumbent continuation result cannot be transferred to
the current portfolio without a separate staged-handoff implementation and
comparison. This note makes no claim that such staging will improve hidden
instances or total equal-resource performance.

## Contest product (titanmcp)

Live judge pad (≠ Commons Shared Pad / ≠ Commons `/mcp`): https://webmcp-pad.vercel.app/ — **titanmcp 1.4.5**, 24 tools, Agent Resources, `syncConsents`. Board: [titanmcp.html](../../../../titanmcp.html). Cite Latch Pad KEEP.
