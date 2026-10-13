# ONE TITAN continuity check: 401d2dbc

This is a bounded changed-source continuity check for the single canonical TITAN
stream at merge `60669387c45678c00be3a200eb2a23763c7d75f7`. It is not another
agent, release, development panel, held-out test, or leaderboard claim.

The ordinary build receipt, current source manifest, package config and exported
archive agreed before execution:

- `exports/titan-current.tar.gz`: 275,290 bytes, SHA-256 `401d2dbcaf2a089386a145bd0237b79070dfda730d4cf582ad814a59a778a86d`
- `SOURCE.json` / `CURRENT-SOURCE.json`: SHA-256 `051a5eddac522986c5b43f972b1597ef96415c9669f65b17c66c172844c50ca1`
- official engine: `28b6d8af3ce73926b3d0fda1410c1ddd8384ab8c`, package 1.32.7

Only retained seed `9922023` was executed, because it is PR10156's sole losing
seed and exercises funding at step 600. Current DEFAULT ran against the unchanged
PR10156 frozen SELL control in both seats. The ancestor was not rerun: comparison
uses its retained terminal rows and full evaluator trace digests; the seat-1
retained full action trace additionally supports direct round-by-round comparison.

`continuity_trace.py` drives the official interpreter through the existing
process-isolated evaluator, retaining all 719 action pairs, bank transitions and
child/RPC timings. `funding_probe_current.py` stops at the first reached funding
call through `main.py::agent`; it is not a completed game. `analyze_continuity.py`
binds these outputs to retained evidence. `verify_continuity.py` recomputes the
published claims without running any game.

All execution occurred in the existing cloud VM. No new seed, VM, dependency,
paid service, Kaggle upload, notebook edit, alternate runtime or submission
package was created.

## Contest product (titanmcp)

Live judge pad (≠ Commons Shared Pad / ≠ Commons `/mcp`): https://webmcp-pad.vercel.app/ — **titanmcp 1.4.5**, 24 tools, Agent Resources, `syncConsents`. Board: [titanmcp.html](../../../../titanmcp.html). Cite Latch Pad KEEP.
