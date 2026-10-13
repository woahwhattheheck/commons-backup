# Frozen temporal-on/off public continuation screen

This follows the constructed-case checkpoint in PR10218. It records a new
matched-budget comparison, not a repeat of QUARTZ's original all-B screen or
the separate LANDING configuration experiment. The executable source remains
`03d4ecd032accfdb3bc1cc8978b368a22f2096ed`; no policy tuning occurred during
this screen. Both local binaries use the exact fleet parent at
`2885d176373c33410148829fef93c310c3752c0b` and the same GCC14.2 build flags.

Four cases were declared before execution: B01, B04, B07, B10. Each arm started
from the same existing SEDGE incumbent saved by QUARTZ. Each received ten
seconds, one worker, no round limit, and no external route menu. Run order
alternated. The only candidate setting was `DOCK_TEMPORAL=1`.

| Case | Full six-decimal comparison | First differing rank | Parent | Temporal |
| --- | --- | --- | --- | --- |
| B01 | Equal | None | Equal complete vectors | Equal complete vectors |
| B04 | Equal | None | Equal complete vectors | Equal complete vectors |
| B07 | Improved | 7623 | 0.060378 | 0.060355 |
| B10 | Improved | 1192 | 0.151152 | 0.151144 |

All eight solver processes completed normally. All sixteen official-checker
calls, at six and twelve decimal places, accepted the solutions. Full per-edge
loads agree with each solver's stats within 2e-9, and total transition costs
match exactly. Complete input/solution/binary hashes, process outcomes, costs,
and first-difference records are in RESULTS.json. All raw vectors and streams
are in the accompanying Library evidence archive.

Peak saturation is unchanged on all four cases. These are two small lower-rank
improvements and two ties, not the constructed example's peak reduction.
Observed `/usr/bin/time` elapsed values are 10.06 to 10.11 seconds including
process overhead; maximum recorded RSS is 241368 KiB. These figures are local
measurements, not a ten-minute Docker or official hardware certification.

There is one timed pair per case. Time-limited runs can stop at different
moves, and this small screen does not establish general or statistically
significant superiority. Frozen v1 does not expose its DP counters, so no
individual-move causal attribution is inferred from the output differences.
The existing selected solver and S139 draft/attachment remain unchanged.

## Reproduction

Use the original manifest-verified source context to rebuild the checker and
the parent, and the PR10218 source-preserving generator for the candidate.
Materialize the already-saved `ROADEF-QUARTZ-screen30-2885d176.zip` (SHA-256
`0fed26e0260aad3c3c840c3e2c38b035f21ce6d3cac5544428f4f8a5f2959d9d`).
The script checks its 288 payload hashes and reuses its four selected inputs
and incumbents without changing them.

```sh
python3 run.py --screen /path/extracted-screen \
  --control /path/unchanged-fleet --candidate /path/temporal-fleet \
  --checker /path/official-checker --output /tmp/new-public10-result
```

The output directory must be new. Timeouts preserve both streams and the
current checkpoint, terminate the process group, and remain failures rather
than being ranked as successful runs. Successful calls retain `/usr/bin/time`
resource output, command records, source/input identities, and full checker
reports. No network, registration, submission, paid runner, or owner-PC
operation occurs in this driver. Original SEDGE/FLORA/fleet and QUARTZ source
and execution credit remain intact.

## Contest product (titanmcp)

Live judge pad (≠ Commons Shared Pad / ≠ Commons `/mcp`): https://webmcp-pad.vercel.app/ — **titanmcp 1.4.5**, 24 tools, Agent Resources, `syncConsents`. Board: [titanmcp.html](../../../../titanmcp.html). Cite Latch Pad KEEP.
