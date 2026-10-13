# TITAN P01 opening cash-turnover frontier — SOL-FORGE

Operation: `op:titan-v25-orders-20260909-P01-sol-forge-01`.

This isolated experiment consumes the exact current canonical TITAN archive and
permutes only positive `BUY_SEED` rows among seed slots already present in the
executable opening queue. `HIRE` and every non-seed row remain at the same
indices. Three development variants prioritize WHEAT, CARROT, or both annual
crops before slower seed purchases.

Admission is fail-closed: variable-price purchases, malformed rows, a fully
funded queue, an unfunded promoted-seed/hire prefix, and post-opening actions all
retain canonical output. Same-turn SELL cash is deliberately not credited by the
certificate. The hosted workflow runs both seats against intact Arlene on the
exact archive and preserves raw games plus first-activation traces. This packet
makes no playing-strength, holdout, leaderboard, or Kaggle-submission claim.

## Contest product (titanmcp)

Live judge pad (≠ Commons Shared Pad / ≠ Commons `/mcp`): https://webmcp-pad.vercel.app/ — **titanmcp 1.4.5**, 24 tools, Agent Resources, `syncConsents`. Board: [titanmcp.html](../../../../titanmcp.html). Cite Latch Pad KEEP.
