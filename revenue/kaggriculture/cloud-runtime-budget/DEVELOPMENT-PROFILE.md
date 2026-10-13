# Exact retained-development actor profile

FINCH consumed TRACE's aligned DELVE development9965001 seat0 control inputs. Both fresh actor processes reproduced all719 original expected actions, with zero mismatches, no action failures and identical sequence SHA256 `09d55e1943d2d7aab3d97ea2d9859080ab0603f171abaf84e4b17145d725bd9a`. The27 consumer tests are separate from those actual policy calls. No engine transition, new game or selection occurred.

## Source and input

Use Library `TITAN-TRACE-DELVE-control-inputs.zip`, file `file_000000002b4081f5a9f64c39a5a19bbc`, ZIP SHA256 `2c4018d3348cef69941f0fc8f557fbee02bb5c263cb6c94d884dfaf1a462e037`. TRACE's delivered candidate gzip is `6d850535bc06fd9d366119365651e789c32ec8a48c96bedaa992fd19a1ff060e`; decoded JSONL is `75f39921d9a749b50b84101f34f8119b51f9646d2ab725d8453f17fdee66083f`. Its receipt binds the original evaluator trajectory `0d9dae2788d2a3cf39bf519a80bc02bef30181258e969310328da5ffcd02eef8` and original terminal52731/52446. Those scores were retained, not recomputed here.

The runtime comes from DELVE's existing `TITAN-DELVE-funded-seed-evidence.zip`, file `file_000000008fe481f58309a3cfde721385`, SHA256 `aaa2d811a919b6b1c2219082753cfe476a0a0fac7567d3ad1d72c9f373a912f9`. In an isolated runtime copy, restore `seed_funding_original.py` as `seed_funding.py`, following TRACE's exact SOURCE-MAP. All29 mapped runtime members match; all20 Python files are unchanged during both profiling passes. Invoke the existing `funded_main.make_agent(funded=False)` once. This is funding OFF, SELL ON, with the archived JUNIPER hook: neither a pristine PR9997 tree nor current-main CEDAR/WREN code.

Use the command in [TRACE-INPUTS.md](TRACE-INPUTS.md), with this runtime, input and receipt. The profiler is source `02689abe983312064b738b39331eafa54715e972`, SHA256 `bb1f2b8045b32d06d1836a53719abd1e508713efbfc6cc4eb9f7e811e7b6cd4a`. The original actor seed20260907 and PYTHONHASHSEED are restored before import; environment seed remains provenance only. TRACE performed the frame/action alignment and original-digest checks; FINCH did not repeat that reconstruction.

## Measured costs

Ordinary target loading through the first attempted action: **42.89ms**. Per-action p99: **20.00ms**. Maximum outer action: **92.49ms at step574**; the reached step683 took **23.13ms**. All719 calls completed without a one-second exceedance. The complete process took7.58s, including input parsing, checks, all calls, serialization and shutdown; that is not startup latency. PeakRSS201124KiB includes the input and harness.

The independent profile sampled steps0,574,583,660,683,697,718 while still executing the full prefix. Nested cumulative costs across those calls are seller308.2ms, projection133.7ms and producer116.4ms. These values include cProfile overhead and overlap through enclosing functions; they are not additive whole-agent stage maxima.

This is a source-matched, expected-action-matched retained development workload, not a new tournament result or hosted deadline certification. The container reports Python3.13.5, a4-CPU cgroup allowance and4GiB memory limit. Direct actor timings exclude DELVE's telemetry-wrapper file writes and original RPC transport, so historical timings cannot be treated as an apples-to-apples speed comparison. The optional scorer, funding-on policy and newer optimizations were not substituted.

`DEVELOPMENT-PROFILE.json` records compact metrics and hashes. Full ordinary/instrumented reports, source readback, TRACE receipt and source map, all27 tests and the earlier three-call wire check are retained in the companion FINCH native-trace delivery. Original PR10052 public-stream results remain unchanged. WIDEFIELD9921001 is still a separate input, not recovered by this work.

## Contest product (titanmcp)

Live judge pad (≠ Commons Shared Pad / ≠ Commons `/mcp`): https://webmcp-pad.vercel.app/ — **titanmcp 1.4.5**, 24 tools, Agent Resources, `syncConsents`. Board: [titanmcp.html](../../../titanmcp.html). Cite Latch Pad KEEP.
