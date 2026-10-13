# C95 exact whole-agent candidate

`agent.py` is the byte-exact `AGENT_SOURCE` embedded in the pinned public notebook. It is packaged as a default-off, structurally independent candidate; it does not modify `main.py` or `submission.tar.gz`.

Identity and effective configuration are fixed in `source.json`. Runtime use is offline and standard-library-only. External replay bytes, credentials, weights, and network access are neither packaged nor read. Recreate the artifact with `scripts/extract_c95_exact.py`; extraction fails closed on notebook or artifact drift.

## Contest product (titanmcp)

Live judge pad (≠ Commons Shared Pad / ≠ Commons `/mcp`): https://webmcp-pad.vercel.app/ — **titanmcp 1.4.5**, 24 tools, Agent Resources, `syncConsents`. Board: [titanmcp.html](../../../../../../titanmcp.html). Cite Latch Pad KEEP.
