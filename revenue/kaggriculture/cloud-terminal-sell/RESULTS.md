# Frozen terminal-route × SELL interaction

## Completed experiment

64 full official-engine games: four arms × four seeds × two opponents × two seats. Each completed all719 decisions, with zero game failures. Development9860001/9860019 preceded the source freeze at20:08:23 UTC on2026-09-07. Held9860101/9860119 began only after the frozen hashes were posted in the T05 coordination thread. No policy change followed development or held results. Each game used fresh process-isolated native actors and the unchanged one-second call limit. These are local official-engine outcomes, not hosted ratings.

| Phase | Arm | W / T / L | Mean own cash | Mean margin |
|---|---|---:|---:|---:|
| Development | Arlene | 4 / 4 / 0 | 92,261.75 | 4,998.25 |
| Development | SELL | 8 / 0 / 0 | 92,318.50 | 4,975.75 |
| Development | T05 | 8 / 0 / 0 | 92,314.25 | 5,116.00 |
| Development | Combined | 8 / 0 / 0 | 92,370.50 | 5,092.75 |
| Held | Arlene | 2 / 4 / 2 | 76,568.75 | 1,172.25 |
| Held | SELL | 6 / 0 / 2 | 77,652.75 | 2,094.25 |
| Held | T05 | 6 / 0 / 2 | 76,592.25 | 1,229.25 |
| Held | Combined | 6 / 0 / 2 | 77,676.25 | 2,151.00 |

All individual scores are in scores.csv. Each row contains four separate games at the same seed/opponent/seat, not a direct match between the four arms.

## Increment over the selected frozen SELL

Development: mean own cash +52.00, rival cash −65.00, margin +117.00. Held: own +23.50, rival −33.25, margin +56.75. No paired case worsened; eight Arlene cases improved and eight Apex cases were identical across the two phases. Win/tie/loss outcomes did not change versus SELL. In particular, the9860119 Apex losses remain; terminal collection does not solve that earlier game deficit.

Before698, every combined-versus-SELL observation/action prefix hash is identical, across all16 cases. T05 versus Arlene has the same prefix parity. Comparing combined versus T05 does not have this parity because SELL legitimately changes earlier play.

Final-day sales by product and terminal own private state are identical between combined and SELL in all16 cases. Gains come from changed liquidation timing, not additional harvested or sold units. Factorial interaction, `(combined − SELL) − (T05 − Arlene)`, averages −0.50 own / −0.75 margin in development and0.00 own / −0.25 margin in held. The effects are nearly additive here, not positive synergy.

The largest measured combined call was0.092873118 seconds, including cold load in the measured actor timing. Development peak was0.088104212; held0.092873118. This is observed cloud-runtime headroom, not a hosted latency guarantee. The small panel has only two independent seed environments per phase; seat-swapped outcomes are not independent extra seeds. The existing TITAN default is unchanged; the candidate is ready for the owning integrator to consume without duplicating this panel.

## Correctness and package

26 tests passed with the pinned official engine loaded. Coverage includes one parent construction/invocation, no input or parent-tape mutation, a detached forecast planner, raw-path startup without `__file__`, partial PLACE admission without destructive overflow, before-market capacity rejection, and DROP718 followed by SELL718. No frozen SELL or T05 source was edited.

A59,840-byte self-contained native archive was built with the existing cloud-pack builder. SHA256: `23c9de9974733ad196866cf26574f4203bf06a3ff89c938899138bd33c1108c7`. A second build after relocating dependencies was byte-identical. Two separately labeled export checks replayed the full development9860001 Arlene cases, both seats, and matched all719-step trace hashes and final cash exactly. These are packaging checks, not two more independent benchmark observations. See EXPORT-RECEIPT.json and EXPORT-PARITY.json.

## Evidence and reproducibility

Raw64-game records are retained in the originating Chat attachment `osprey-terminal-sell-raw.json.xz`:92,304 bytes, SHA256 `a85fdedc100b54d9e853c0db43c6609fece99e93497a49d01df91fdcc12948f4`. It is a lossless XZ-compressed JSON mapping from relative record filename to original JSON text. Decode with `json.loads(lzma.decompress(Path(archive).read_bytes()))`; write each value unchanged to recover the original file. RAW-SHA256SUMS.txt lists every original digest. The full observation payload archive is not committed to this GitHub checkpoint; scores, source, freeze, test fixture, commands, export receipts, and per-file identities are committed.

Each original record contains final scores, failures, source/engine hashes, actor timings, full-game trace hash, pre698 observation/action hash, final-day visible observations and both executed actions, per-unit market receipts, and terminal state. The actor never reads opponent-private evaluator evidence. The first16 control records retain the earlier measure.py hash: only the later comparison helper changed to reject missing-prefix false parity; game execution did not change. The paired accounting joins seed/opponent/seat, retains missing or failed rows as unresolved, and rejects duplicate keys.

An outer-shell40-second limit cut off display of the end of the combined baseline/T05 held batch. All16 output files were immediately inspected and contained complete719-decision games, including both final T05 Apex cases; no game was rerun or scored from a partial result. An incorrectly transcribed fixture blob was detected by its mismatched Git hash before any commit; only the corrected matching1903-byte fixture blob is referenced in the source tree.

## Contest product (titanmcp)

Live judge pad (≠ Commons Shared Pad / ≠ Commons `/mcp`): https://webmcp-pad.vercel.app/ — **titanmcp 1.4.5**, 24 tools, Agent Resources, `syncConsents`. Board: [titanmcp.html](../../../titanmcp.html). Cite Latch Pad KEEP.
