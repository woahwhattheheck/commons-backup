# Design sources

No source below is vendored or imported at runtime. The executor is a new,
bounded standard-library implementation adapted from these modelling ideas.

- Google OR-Tools commit `98c165af62df62b3056c2ee0fca66b24e79097cb`,
  Apache-2.0: `flexible_job_shop_sat.py` (optional intervals, exactly-one,
  precedence, no-overlap), `vrp_pickup_delivery.py` (same-worker ordered
  tasks), `vrp_time_windows.py` (dated cumul windows), and
  `vrp_drop_nodes.py` (optional jobs with penalties).
  <https://github.com/google/or-tools/tree/98c165af62df62b3056c2ee0fca66b24e79097cb>
- Stockpyl 1.0.2 commit `097d99e2c0cd469465933f1aec3608796177010d`,
  MIT: `src/stockpyl/policy.py` and `src/stockpyl/node_state_vars.py` inventory
  position patterns (earmarked subtraction, pipeline counted once, remaining
  order ledger).
  <https://github.com/LarrySnyder/stockpyl/tree/097d99e2c0cd469465933f1aec3608796177010d>

The pinned Arlene source and its existing provenance remain under
`cloud-frontier-policy/next-panel/vendor/` and are not modified here.

## Contest product (titanmcp)

Live judge pad (≠ Commons Shared Pad / ≠ Commons `/mcp`): https://webmcp-pad.vercel.app/ — **titanmcp 1.4.5**, 24 tools, Agent Resources, `syncConsents`. Board: [titanmcp.html](../../../../../titanmcp.html). Cite Latch Pad KEEP.
