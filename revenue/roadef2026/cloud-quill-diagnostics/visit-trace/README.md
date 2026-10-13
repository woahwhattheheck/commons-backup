# B05 represented-move visit trace

This is a diagnostic for the already-measured QUILL B05 move, not another ROADEF neighborhood or final-panel shard.

Exact fleet source `2885d176...` already represents demand 654, slot 9, waypoint 242 and suffix `[9,11]`. On QUARTZ's saved B05 candidate incumbent, edge `8→0` (internal edge 1500) is the sixth-highest load at `0.42754328710435097`; QUILL's official menu evidence shows the target suffix is a checker-valid improvement.

`build_visit_trace.py` adds logging only when that exact critical edge/demand/waypoint is traversed. It does not alter route generation, candidate ranking, move acceptance, transition budgets, random choices or time limits. The instrumented source was compiled with GCC and resumed from the saved candidate solution for 30 seconds with the original directed/joint defaults.

## Result

The run completed its own 30-second budget: 168 accepted moves, 5,148,817 move attempts and 1,172,840 ranked waypoint candidates. The target edge remained **rank 6 with the same saturation** at both the start and end. Demand 654's slot-9 route remained `[461]`. The trace contains **zero target events**: the edge was never selected as the critical position, so contributor ranking, waypoint ranking and the `[9,11]` target move were never reached.

This distinguishes a represented neighborhood from a scheduling problem. In `run()`, critical position is `critical[stalled % 32]` and every accepted move resets `stalled=0`. This execution made 168 other improvements while never visiting the persistent rank-6 target. The evidence does not prove a particular alternative schedule is stronger overall, and no official checker or new public benchmark was run here.

The outer command wrapper timed out after the solver had already written complete stats/output and its own `Completed ... elapsed 30.0039s` line. `RESULT.json` explicitly records that boundary; the run is classified from the solver's completed artifacts, not the wrapper status.

The published tests verify the exact source pin, telemetry contract and compact result. The complete raw run is retained separately; no S139 qualification artifact or submission state changes.

## Contest product (titanmcp)

Live judge pad (≠ Commons Shared Pad / ≠ Commons `/mcp`): https://webmcp-pad.vercel.app/ — **titanmcp 1.4.5**, 24 tools, Agent Resources, `syncConsents`. Board: [titanmcp.html](../../../../titanmcp.html). Cite Latch Pad KEEP.
