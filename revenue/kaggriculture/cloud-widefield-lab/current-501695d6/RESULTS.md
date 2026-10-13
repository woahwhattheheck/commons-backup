# Current `501695d6` continuity result

## Outcome

The current canonical TITAN archive is behaviorally identical to its immediate
thread-safe predecessor on this bounded development comparison.

- Current archive: `501695d66c2642d452180b2f129d181ba0ede02647b70ddd74ebd82e3762011c`
  (290,630 bytes; 78 runtime files).
- Prior archive: `26e19f9abe986ab93873ff993cea38042921d685f099d65a96fd5edc795a43b2`
  (289,487 bytes; 78 runtime files).
- Seeds: `9925001`, `9925019`; both seats.
- Opponent in both arms: the byte-identical packaged frozen SELL controller,
  `frozen_selected.py::agent`.
- Official-interpreter games: 4 per arm, 8 total; zero failures.
- Both arms: 4W/0T/0L, mean margin +240.
- Exact parity: 4/4 terminal-score pairs and 4/4 complete trace hashes match.
- Current maximum candidate call: 0.063923 s; maximum parent-observed RPC: 0.064940 s.

This is local development continuity evidence. It is not a hosted result, held
panel, leaderboard result, or independent strength estimate.

## Archive and transport binding

The current bytes came from the existing successful PR10364 canonical-check
artifact `10043286352`, not from a rebuild. The downloaded artifact ZIP has
SHA-256 `52b64c227f4c400408af0c3360681a9c26006db4e57c975c516e7396eda9c4bc`.
Its `PACKAGE-TRANSFER.json` binds the checked package to PR head
`a2fdd03e161e2e469883a0916b46768a156aa7a7`; the workflow checked 292 source
files with no changed paths. The copied current source manifest has SHA-256
`6ebc0f3c6e6d6e9815623920cbbaacd49efdc5bb96acb6def2ad8677b4bff555`.

The prior bytes came from the existing successful PR10343 canonical-check
artifact `10042959443`; artifact ZIP SHA-256
`c229489bcd45de2ff76fa8542ba09c4370da5dcdb01d1df97da50e9c95742257`.

Both tars contain the same 79 regular-file paths. Only these members differ:

1. `SOURCE.json` (the package manifest), and
2. `reference/titan-history/selected_action_history.py`.

The public configuration is byte-identical and keeps `terminal_history=false`.
The comparison therefore checks that adopting the newer default-off history
source did not alter the selected default trajectory on the sampled games.

## Exact receipts

`results/continuity.json` SHA-256:
`6c6e8bf51090edbb37cc7fb851af56f7956239f85ff1b0e9f59701ac0babc493`

Original evaluator reports are retained losslessly as deterministic gzip files:

- `results/current.json.gz` decompresses to SHA-256
  `0642a94b82d94448ac5e941c8f8c24269280908d05ca04b41302b950fadda24c`
- `results/prior.json.gz` decompresses to SHA-256
  `89c8c03712581b913b3c9f3c2b524b087b8a701e125d65f158e5d0f1c4f260df`

Pinned execution inputs recorded in the report:

- evaluator: `e30b3108e0027477ab7ddbc057892a241c41a1f2b38f72caf267477877c4333c`
- loader: `cd113a94ae99b03492502e425bdcf09c3db17a2aa2a8fd866f0d78caec9e311e`
- official engine files: see `results/continuity.json`
- agent-process RNG seed: `20260908`

## Reproduce

Use the two exact tar files copied from the successful canonical-check
artifacts, then run:

```bash
python -B run_continuity.py \
  --current-archive /path/to/501695d6.tar.gz \
  --prior-archive /path/to/26e19f9a.tar.gz \
  --seeds 9925001,9925019 \
  --output-dir /tmp/current-501695d6-results
```

The runner is offline, safely extracts regular files only, verifies both archive
hashes, requires identical public configuration and frozen-opponent bytes, runs
both arms with the packaged pinned evaluator/engine, and exits nonzero unless
all games complete with equal scores and full trace hashes.
## Runner self-check

The committed runner was executed again from the two immutable canonical-check
archives in a fresh output directory. It exited `0`, completed all eight games,
and reproduced the same four terminal-score pairs and complete trace hashes.
The reproduction receipt is `REPRODUCER-TEST.json` (runner SHA-256
`bc67e772d706d009588f74f84161ff4dceb8cd01ab36a9d97de97a1ff841d736`). Timing fields varied between executions and are deliberately
not part of the equality contract.

A negative identity test supplied an all-zero expected current-archive digest.
The runner exited nonzero before extraction or game execution and reported the
actual `501695d6...` digest. `--help` also completed successfully. These checks
show that the published command is runnable and fails closed on archive drift.

## Contest product (titanmcp)

Live judge pad (≠ Commons Shared Pad / ≠ Commons `/mcp`): https://webmcp-pad.vercel.app/ — **titanmcp 1.4.5**, 24 tools, Agent Resources, `syncConsents`. Board: [titanmcp.html](../../../../titanmcp.html). Cite Latch Pad KEEP.
