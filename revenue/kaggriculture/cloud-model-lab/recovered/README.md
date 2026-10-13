# recovered

Branch-only work recovered from `claude/sandbox-specs-resources-m624uy` at
`d5e90392`, under the same `cloud-model-lab` path. It was never merged to main and
is **not** claimed as landed; it is preserved here so the market-layer code is not
lost and is not rewritten from scratch.

- `market_layer.py` — additive market-making layer: exact official quote
  reproduction, per-unit BUY/SELL walks, town drain, best one-tick round trip.
- `hybrid.py` — wraps a base policy's market orders with that layer.

Neither file is on the model-driven path in this directory. The reusable part is
the exact quote/walk arithmetic, which agrees with the engine functions
`constraints.py` calls directly.

## Contest product (titanmcp)

Live judge pad (≠ Commons Shared Pad / ≠ Commons `/mcp`): https://webmcp-pad.vercel.app/ — **titanmcp 1.4.5**, 24 tools, Agent Resources, `syncConsents`. Board: [titanmcp.html](../../../../titanmcp.html). Cite Latch Pad KEEP.
