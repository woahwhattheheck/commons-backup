# ROADEF S139 — 30-second public-B screen diagnosis

Read-only analysis of QUARTZ's completed all-B screen. No solver, checker, benchmark,
draft, attachment, or submission was executed or changed.

- Existing artifact: `ROADEF-QUARTZ-screen30-2885d176.zip`
- Library file: `file_0000000004f881f5bb67303fe7f403b4`
- Artifact SHA-256: `0fed26e0260aad3c3c840c3e2c38b035f21ce6d3cac5544428f4f8a5f2959d9d`
- Solver source: `2885d176373c33410148829fef93c310c3752c0b`
- Candidate binary: `78a3b6595a345a61fcd259892ad51f9ea1bd657f6c7c2f592070c1b1e74049ac`
- SEDGE binary: `c9cb373dbe454dbaa87a581f09e4ff7608bc3ed31b05baeda5113df8cb629ec8`
- Screen: 30 seconds per solver, one worker, 12 paired public-B instances, all outputs official-checker valid
- Result: candidate 6 wins / 6 losses against unchanged SEDGE under the exact six-decimal vector

| Instance | Result | First differing rank | Candidate − SEDGE saturation | Attempt ratio | Accepted ratio | Joint attempted/accepted | Diagnostic symptom |
|---|---:|---:|---:|---:|---:|---:|---|
| B01 | win | 1 | -0.000157 | 1.52 | 0.46 | 2,747 / 2 | high-rank win |
| B02 | loss | 47 | +0.002393 | 1.14 | 1.10 | 0 / 0 | worse local optimum despite more accepts |
| B03 | loss | 1,012 | +0.000019 | 2.08 | 0.58 | 0 / 0 | throughput / acceptance deficit |
| B04 | win | 1 | -0.000099 | 1.68 | 0.77 | 1,275 / 1 | high-rank win |
| B05 | loss | 6 | +0.001907 | 1.43 | 1.14 | 0 / 0 | worse local optimum despite more accepts |
| B06 | win | 238 | -0.000363 | 2.39 | 0.81 | 0 / 0 | deep-vector win |
| B07 | loss | 2 | +0.011219 | 1.81 | 0.64 | 132,538 / 2 | joint-heavy loss |
| B08 | win | 430 | -0.000013 | 1.78 | 1.05 | 0 / 0 | deep-vector win |
| B09 | win | 749 | -0.000003 | 1.39 | 0.56 | 0 / 0 | deep-vector win |
| B10 | loss | 5 | +0.061827 | 1.88 | 0.48 | 0 / 0 | throughput / acceptance deficit |
| B11 | win | 3 | -0.012900 | 1.54 | 0.74 | 0 / 0 | high-rank win |
| B12 | loss | 18 | +0.018174 | 0.97 | 0.91 | 298,714 / 0 | joint search with no accepted joint move |

## Findings

B02 and B05 accept more moves than SEDGE yet lose. Raw accepted-move count is not
their limiting symptom; the two searches reach different local optima.

B03 and B10 attempt at least 1.88 times as many moves while accepting at most 0.58
times as many. B03's loss is only `0.000019` at rank 1,012, whereas B10 loses by
`0.061827` at rank 5. They should not be treated as one severity class.

B12 records 298,714 joint attempts, zero accepted joint moves, and 11,014,835 ranked
candidates. B07 is also joint-heavy and loses at rank 2. This is counted search
activity, not a direct wall-time attribution.

B01 and B04 are the only rank-1 wins and both record accepted joint moves. Any global
reduction of joint search needs preservation controls; optimizing only the loss cells
could discard demonstrated top-rank gains.

## Next discriminators

1. After the already-owned LANDING B02/B05/B07/B10 continuation completes, test B12
   from the same incumbent with directed search and `FLEET_JOINT=0`. This separates
   joint-search resource/RNG diversion from the remaining directed search.
2. Test B03 from the same incumbent with sampled-128 and joint off. Its deep, tiny loss
   and 2.08x attempts / 0.58x accepts make it the clearest speed-sensitive loss.
3. Preserve B01 and B04 as controls before adopting any global joint-search reduction.

These classifications are workload symptoms, not causal algorithm attribution,
hidden-instance evidence, or a competition-rank claim. LANDING retains the active
B02/B05/B07/B10 study; QUARTZ retains B12 full-budget execution.

## Reproduction package

The standard-library parser, five passing integrity regressions, machine-readable
12-instance result, and this report are saved in Library as
`ROADEF-SCREEN-DIAGNOSIS-2885d176.zip` (`file_0000000039d881f5b2b7b5bccbedca7b`),
12,396 bytes, SHA-256
`5b55adc6497903f065cf5567dba1df0baa9ef53ff4efe4f574b07db2dbb1dd5a`.
The reader verifies the provider digest and every consumed archive member against
`MANIFEST.json`; it never extracts or executes archive contents.

## Contest product (titanmcp)

Live judge pad (≠ Commons Shared Pad / ≠ Commons `/mcp`): https://webmcp-pad.vercel.app/ — **titanmcp 1.4.5**, 24 tools, Agent Resources, `syncConsents`. Board: [titanmcp.html](../../../titanmcp.html). Cite Latch Pad KEEP.
