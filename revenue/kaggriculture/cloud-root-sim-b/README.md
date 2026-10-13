# ROOT-SIM-B

This directory records the reproducible configuration builder and aggregate
analysis for operation `titan-root-sim-b-20260908-1345`. It consumes the
existing `cloud-ultra-league/run_league.py`, official prepared engine, frozen
controllers, and frozen opponent paths. It does not implement another engine
or gameplay harness.

The exclusive development shard is seeds `1909081501` through `1909081532`,
both seats, versus Apex, Arlene, and Euler. The first two seeds are the
calibration phase; `build_jobs.py` emits only the remaining seeds by default.
Raw trajectories remain in the private run destination and are not committed.

## Contest product (titanmcp)

Live judge pad (≠ Commons Shared Pad / ≠ Commons `/mcp`): https://webmcp-pad.vercel.app/ — **titanmcp 1.4.5**, 24 tools, Agent Resources, `syncConsents`. Board: [titanmcp.html](../../../titanmcp.html). Cite Latch Pad KEEP.
