# W01 live V2 replay intake

Reusable, standard-library parser for TITAN FRONTIER W01. It converts public
Kaggriculture replay files into a causal per-transition timeline without
publishing or embedding replay bodies.

For transition `t >= 1`, the action stored in `steps[t]` is paired with
`steps[t-1].observation` as pre-state and `steps[t].observation` as post-state.
This convention is source-checked against real inventory/cash changes before
publication. The parser preserves `info.seed` separately from the normally-null
`configuration.seed`, TeamNames order, own seat, rewards, statuses and exact raw
hashes. It emits Bryce's own private observation but never rival-private state.

The first W01 data tranche executed this parser over 11 compact LIVE V2 loss
replays: 7,909 transitions, with exact metadata agreement against an independent
72-row Slack source table. The portable raw/data bundle is retained privately in
the shared Library/Slack work surfaces; raw replay bytes are deliberately not
committed here.

Frontier availability from that tranche: W04 4/4, W03 4/6 and W02 3/4. Three
loss replays (`107137714`, `107138580`, `107139582`) existed in Slack only as
oversized raw files for this VM's inline reader, so they remain explicit
portable-byte gaps rather than being called absent.

Reproduce parser contracts:

```sh
cd revenue/kaggriculture/cloud-v25-w01-live-data
python -B -m unittest -v test_replay_parser
```

Real-run counts/source bindings are in `RESULTS.json`. This component performs
no provider download, game, policy selection, canonical archive change or
submission operation.

## Contest product (titanmcp)

Live judge pad (≠ Commons Shared Pad / ≠ Commons `/mcp`): https://webmcp-pad.vercel.app/ — **titanmcp 1.4.5**, 24 tools, Agent Resources, `syncConsents`. Board: [titanmcp.html](../../../titanmcp.html). Cite Latch Pad KEEP.
