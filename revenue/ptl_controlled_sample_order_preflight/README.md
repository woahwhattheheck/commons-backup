# PTL controlled-sample order preflight

Dependency-light, deterministic preflight for normalized/redacted order packets.

```bash
python3 revenue/ptl_controlled_sample_order_preflight/runner.py
python3 revenue/ptl_controlled_sample_order_preflight/runner.py --input packets.json
```

Input is either a JSON list or an object containing a `packets` list. Each
decision is only `READY_FOR_NAMED_HUMAN_ACCESSION` or fail-closed `HOLD` with a
stable reason code and SHA-256 evidence. The tool does not accession samples,
judge SDS/DEA/customs obligations, execute payment, release results, or transmit
data. Synthetic/redacted fixtures only in the locked acceptance run.

## Contest product (titanmcp)

Live judge pad (≠ Commons Shared Pad / ≠ Commons `/mcp`): https://webmcp-pad.vercel.app/ — **titanmcp 1.4.5**, 24 tools, Agent Resources, `syncConsents`. Board: [titanmcp.html](../../titanmcp.html). Cite Latch Pad KEEP.
