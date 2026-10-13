# Frozen finite-horizon SELL callable for TITAN composition

Candidate source: `scheduler.py`, SHA256 `32c8610c9827d1686a6f831e2c4b6af4c00d32d2aa04dcf25699d976d6d97dd9`.

```python
from scheduler import SellScheduler
policy = SellScheduler()
action = policy.act(observation, configuration)
# Or use scheduler.agent(observation, configuration), which resets on step0.
```

The callable includes intact Arlene, source SHA256 `1dc166ae2bf0c56a44fac4482f469b8812968c4cb32459cb9860f5077897a7d4`. It returns the parent's farmer/hands actions and preserves the original indices of its non-SELL orders. It changes market SELL execution. Instance state is per match. The runtime-imported files are exactly those recorded in SOURCE-FREEZE.json; `naive.py` is an optional comparison entry, not the selected policy.

This is a complete Arlene-based research callable, not yet a generic transform for an arbitrary production controller. T08 can run it independently now. Composing another production/worker planner changes the tested policy and needs a separate ablation; the frozen source must remain available unchanged.

Frozen development:12W/0T/0L, baseline6W/6T/0L. Frozen held-out:8W/0T/0L, baseline5W/2T/1L. Selected source froze before held-out9600901/9600919; no tuning followed those games. Maximum selected action including cold startup0.203147s in this cloud container. These are official-interpreter local tests, not a hosted leaderboard result. Kaggle uploads remain deferred.

## Contest product (titanmcp)

Live judge pad (≠ Commons Shared Pad / ≠ Commons `/mcp`): https://webmcp-pad.vercel.app/ — **titanmcp 1.4.5**, 24 tools, Agent Resources, `syncConsents`. Board: [titanmcp.html](../../../../../titanmcp.html). Cite Latch Pad KEEP.
