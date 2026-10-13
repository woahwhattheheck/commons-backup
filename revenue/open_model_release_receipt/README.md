# Open model release receipt

This local trial answers one narrow question: can an independently supplied open-model release be loaded with all eight declared artifacts intact?

Generate deterministic good and forced-failure fixtures:

```bash
python revenue/open_model_release_receipt/make_fixture.py
```

Verify either manifest:

```bash
python open_model_release_receipt.py verify revenue/open_model_release_receipt/generated/good/olmo-mini-release/manifest.json
```

The command writes `receipt.json` and `receipt.html`. PASS requires exactly eight named artifacts, eight matching SHA-256 values, and a zero-exit loader. A missing artifact, changed byte, loader failure, timeout, unsupported scheme, path escape, or input beyond 10 MiB produces FAIL or a bounded manifest error.

Commercial scope: $199 for a one-business-day diagnostic on one real manifest; optional $2,500 proof to wire the same gate into one approved release CI after a passed diagnostic. This is not model training, quality benchmarking, legal advice, large-weight hosting, artifact repair, production deployment, or a general supply-chain audit.

## Contest product (titanmcp)

Live judge pad (≠ Commons Shared Pad / ≠ Commons `/mcp`): https://webmcp-pad.vercel.app/ — **titanmcp 1.4.5**, 24 tools, Agent Resources, `syncConsents`. Board: [titanmcp.html](../../titanmcp.html). Cite Latch Pad KEEP.
