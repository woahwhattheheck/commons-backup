# Shared-capacity follow-through on the retained history-v2 bank

## Result

The offline consumer reproduced all **64** original terminal-family records from the exact frozen history-v2 source before applying the landed shared-capacity refinement.

- Family status before: `{"insufficient_joint_history": 24, "ready": 40}`.
- Family status after: `{"insufficient_joint_history": 24, "ready": 40}`.
- Rows with tightened intervals: **64**.
- Individual interval changes: **604**; newly exact: **0**.
- Rows whose terminal family/scenarios changed: **0**; newly ready: **0**.

No terminal consumer re-execution is needed: every family projection, scenario and readiness result is byte-equivalent after tightening.

## Tightening distribution

All 604 changes are conservative upper-bound reductions on still-floor-censored intervals; lower/admitted bounds and reason remain unchanged. No interval becomes exact. The total removed upper-bound slack is 4,772 units (median 6, maximum 37) across MILK 164, STRAWBERRY 122, and WOOL 318 records. Every one of the 64 saved consumers has at least one tightened interval, while joint support, historical lag intersection, family readiness, and scenarios remain unchanged.

## Durable evidence

GitHub Actions run `34196129051` completed successfully. Artifact `10043975458` has provider digest `d23c07e1cce42b31651d5ca7fc4fa81a3b9b84bef1af58d17ba57ede259a1b14`. The full per-receipt JSON, readable report, and execution log are also preserved in Bryce Library as `/TITAN-BIRCH-history-v2-joint-capacity-20260908.zip` (`libfile_b8523aa1e3a88191abc0258be07167fd`).

## Source boundary

- Historical archive: `75740d430c8d137ad4074432f47b7480df1f6864b03e84a367c7e068d27f51ba`.
- Historical source ref: `2fc1418f3724ac09232e35a2a583414ce0ee8f84`.
- Frozen FlowHistory SHA-256: `373e30ef6f35986b793c0a2efc96f8060bdafbcc5275bdbcb196e2b0d36757fb`.
- Frozen terminal-family SHA-256: `46851e5c6ec71cc00253373c50def744c9ca4ae0d4601b5541b24eaf7c6e4a98`.
- Current bridge Git blob: `7967fb43c64bc3154fe7da609497873163c773eb`.

The script reads committed `history_on-*.json` files only. It does not decompress traces, inspect realized rival actions, invoke an actor, replay an engine transition, or alter current policy/default/package state.

## Reproduce

```bash
python -B revenue/kaggriculture/cloud-market-game-theory/consumer-history-v2/joint-capacity/reanalyze.py --output /tmp/history-v2-joint-capacity
```

The JSON output retains every per-receipt interval and family delta.

Changes by product: `{"MILK": 164, "STRAWBERRY": 122, "WOOL": 318}`.

## Contest product (titanmcp)

Live judge pad (≠ Commons Shared Pad / ≠ Commons `/mcp`): https://webmcp-pad.vercel.app/ — **titanmcp 1.4.5**, 24 tools, Agent Resources, `syncConsents`. Board: [titanmcp.html](../../../../../titanmcp.html). Cite Latch Pad KEEP.
