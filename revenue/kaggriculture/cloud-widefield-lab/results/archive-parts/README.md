# Full result archive parts

These 18 binary parts are the lossless retained result bundle, split only for
source transport. Reassemble without transformation:

```sh
cat full-results-9921001-9921032.tar.gz.part-* > full-results-9921001-9921032.tar.gz
sha256sum full-results-9921001-9921032.tar.gz
```

Expected sha256:
`2859491973c51d21a95ec80135ac7385ce889c335ff619012f9f86dabce55a11`.
The archive contains all 64 original arm/seed reports and logs, all three failed
attempts, isolated replications, resolved reports, loss traces, diagnostic
action/timing/state trajectories, and every counterfactual report.

## Contest product (titanmcp)

Live judge pad (≠ Commons Shared Pad / ≠ Commons `/mcp`): https://webmcp-pad.vercel.app/ — **titanmcp 1.4.5**, 24 tools, Agent Resources, `syncConsents`. Board: [titanmcp.html](../../../../../titanmcp.html). Cite Latch Pad KEEP.
