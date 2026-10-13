# ROOT-SIM-C results

Operation `titan-root-sim-c-20260908-1345` completed all 384 logical games on
development seeds 1909081601–1909081632, against Apex, Arlene and Euler in both
seats. Every accepted game used the official engine at
`28b6d8af3ce73926b3d0fda1410c1ddd8384ab8c`, configured for 720 steps, and
recorded 719 action rounds plus all 720 engine transitions. There were no errors
or timeouts among the 384 logical completions.

Frozen controllers:

- CURRENT archive SHA-256 `499989ab907331d4c0c990af2ab3703e6731dc83078964aca8563ea5a069e48e`,
  313471 bytes.
- historical v1 archive SHA-256
  `7b58fa06da778b1519b81d509d28dff3481b3bbcc7a2d656e8bdfe4a22540524`.

| Opponent | CURRENT W/T/L | v1 W/T/L | CURRENT mean cash | v1 mean cash | Paired margin delta (95% seed bootstrap) |
|---|---:|---:|---:|---:|---:|
| Apex | 61/0/3 | 61/0/3 | 90030.125 | 90023.828 | +5.984 [5.203, 6.922] |
| Arlene | 63/0/1 | 63/0/1 | 90827.656 | 90821.734 | +5.734 [5.031, 6.703] |
| Euler | 62/0/2 | 62/0/2 | 115424.797 | 115442.859 | -2.875 [-23.188, 8.125] |
| All | 186/0/6 | 186/0/6 | 98760.859 | 98762.807 | +2.948 [-3.385, 6.521] |

This shard shows no W/D/L change and does not support a broad-strength claim.
The positive Apex and Arlene paired-margin effects are narrow and statistically
stable in this seed sample. The combined interval crosses zero because one Euler
seed exposes a material adverse interaction.

## Exact causal handoff

Euler seed 1909081615, in both seats, finished at CURRENT 120128–28616 versus
historical 120894–29085 from the corresponding candidate seat: CURRENT lost 766
own cash and 297 margin while retaining the win. The first candidate-action
difference is transition 122: CURRENT's enabled `redundant_hire` transform in
`titan_runtime.py::_redundant_hire_selected` replaces the second `HIRE` with its
documented no-order marker `SELL WHEAT 0`, initially saving 5 cash. The policies
next diverge at transition 449, where CURRENT sells 2 WOOL while v1 holds it, and
at transition 454 CURRENT sells 18 MILK while v1 holds it. The shifted inventory
then changes later sale timing and finishes 766 behind v1. This is the concrete
case for the current runtime/performance owner: the bounded physical redundancy
certificate is not a terminal economic certificate, and the downstream frozen
seller is sensitive to the removed persistent hand/inventory path.

All six logical losses were shared by both controllers. Two losses (Arlene and
Apex at seed 1909081602 seat 0) had identical candidate actions and final scores;
the other four improved by 5 margin under CURRENT and did not flip outcome.

## Resource and setup audit

CURRENT candidate calls: mean 7.006 ms, p95 24.391 ms, p99 45.746 ms, maximum
267.279 ms. Candidate RPC: mean 9.298 ms, p99 51.169 ms, maximum 296.166 ms.
Historical candidate calls: mean 4.033 ms, p99 19.964 ms, maximum 162.498 ms;
RPC p99 21.851 ms, maximum 172.603 ms.

The first cold calibration retained three Apex step-0 timeouts caused by Apex's
unchanged lazy C++ compilation inside the one-second RPC. Apex was then prebuilt
through its source-supported `_library()` path; `agent.so` SHA-256 is
`d132de713c1ae77ee1498c055deb864d942b101b670c35125636cc66e4e6deae`.
The first three-game remaining-CURRENT job later retained three contention
timeouts. It was stopped, and every failed cell plus every unattempted cell was
run under an explicit two-game continuation; all completed. Those six attempts
remain failures and are not scored as wins or included in the 384 logical-game
statistics.

Raw trajectories and failure observations remain private. `RESULTS.json`
contains the aggregate, concise loss cases, timing statistics and sanitized
failure receipts.

## Contest product (titanmcp)

Live judge pad (≠ Commons Shared Pad / ≠ Commons `/mcp`): https://webmcp-pad.vercel.app/ — **titanmcp 1.4.5**, 24 tools, Agent Resources, `syncConsents`. Board: [titanmcp.html](../../../titanmcp.html). Cite Latch Pad KEEP.
