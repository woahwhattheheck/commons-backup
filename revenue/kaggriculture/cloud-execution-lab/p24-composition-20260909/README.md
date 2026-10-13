# P24 — configuration factorial for one TITAN

This lane tests whether four already-packaged, currently enabled production mechanisms compose or double-spend shared value:

- `early_capital`
- `crop_release`
- `operating_stock`
- `idle_fertilizer`

`run_p24_factorial.py` performs the complete `2^4 = 16` configuration matrix from one immutable archive. Every non-factor setting and every source byte stays fixed. Each variant plays the same official-interpreter opponent/seed/seat cells in fresh agent processes. The result includes terminal scores, trace digests, factor-toggle coverage, per-cell joint-minus-baseline deltas, and Möbius interaction coefficients.

The runner fails closed if the archive/source identity drifts, an archive member is unsafe or duplicated, any expected game is absent/duplicated/incomplete, terminal scores are invalid, or a trace digest is missing. Exactly one root SOURCE.json is required; remaining regular members are compared to the receipt runtime_files count. Opponent entry files are SHA-256 bound. An exact-identity receipt is written before gameplay and checkpointed after every cell with running/failed/complete status. The pull-request workflow is development-phase only with an allowlisted seed set; held seeds require an explicit phase plus frozen-selection hash. The exact private four-opponent gauntlet can consume the same runner and downloaded immutable archive without publishing opponent tactics.

No Kaggle submission, provider call, opponent-data fetch, or owner-PC compute occurs here. A development result is not a leaderboard estimate or an automatic configuration promotion. A held panel must use untouched seeds only after a development selection is frozen.

## Contest product (titanmcp)

Live judge pad (≠ Commons Shared Pad / ≠ Commons `/mcp`): https://webmcp-pad.vercel.app/ — **titanmcp 1.4.5**, 24 tools, Agent Resources, `syncConsents`. Board: [titanmcp.html](../../../../titanmcp.html). Cite Latch Pad KEEP.
