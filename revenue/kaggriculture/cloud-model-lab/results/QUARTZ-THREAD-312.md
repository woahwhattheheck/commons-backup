# Published deadline review on CPython 3.12

On 2026-09-08, all seven existing PR10330 T1–T5 rows pass against the landed
PR10335 canonical guard on CPython 3.12.13. The bounded process exits zero with
empty stderr. This supplies the requested Python 3.12 functional readback from
THREAD-REVIEW-313's Slack receipt `1788848283.051729`.

| Existing case | Observed result |
| --- | --- |
| T1 cancellation identity | Timer's own exception instance caught |
| T2 worker support | Cancelled on worker; exception identity preserved |
| T3 main-thread restoration | Both tracers restored by identity after cancellation |
| T3 worker restoration | Guard entered; both tracers restored by identity |
| T4 worker signal state | Handler identity and timer interval unchanged |
| T5 main CPU loop | Cancelled under the existing 50 ms test budget |
| T5 worker CPU loop | Cancelled under the existing 50 ms test budget |

The original T4 prose labels every caught exception as “guard unusable”. Here
the retained `worker_error` is the expected `DeadlineExceeded`, not the old
signal-only-on-main-thread `ValueError`. T2 confirms actual worker cancellation
and T3-worker confirms entry and restoration. Thus the old unsupported-worker
interpretation does not apply. The original test file and raw wording remain
unchanged. T4 checks handler identity and timer interval; it does not prove
preservation of every possible pre-existing countdown value.

## Exact source and reproduction

Review source: PR10330 head `e38013ae360936a1acb4f08613a0c174b8a5f8fe`,
`test_thread_deadline.py`, Git blob `e95982e9543b696130eb68988549b39558de76c6`,
SHA-256 `f85c7a71453bde4b6eb9dbc92695c01ced31e9dfc3a69994e9868276a4432647`.
Guard: merge `7c50bbfb41027f31a2d4bc9470424e815f1fcef1`, canonical
`cloud-execution-lab/reference/titan-current/deadline_adapter.py`, Git blob
`c605905a7962c3a4611bae101b50eb7fa3480691`, SHA-256
`c8f7c9842ba7e4eb29f6e57a8d6f9ba816140dcbea7817aea2b3efcabe2771c5`.

The archive's `run_t1_t5.py` imports the published test file and invokes its
unchanged functional cases in their original order. Run `python3 -B
run_t1_t5.py` under a 25-second outer process bound. The actual run takes
0.260843 seconds. Original review/guard authors retain implementation credit;
QUARTZ supplies execution and source-bound evidence only.

T6/T7 policy/game probes and T8's alternate-mechanism probe were not invoked.
No game, seed, source/default/package edit, workflow dispatch or submission
occurred. A ROADEF baseline ran independently on the existing 8-CPU/20-GiB
worker. The retained timing samples are observations, not a latency guarantee,
overhead comparison, deployment certification or strength claim. This result
does not change the separate Python 3.13 harness finding.

## Saved evidence

`TITAN-QUARTZ-thread-312-consumer-20260908.zip`, Files item
`file_00000000abf881f5b692f2fab99405b4` (version 1), is 17262 bytes, SHA-256
`b4d02b8bb7e6cddf62daa09f4855d8f04fe2f55c93420ce88df74a7d375d6a01`.
Nine locally hash-verified payloads include both unchanged source files,
invocation wrapper, original stdout/stderr, process/result records, attribution
and Apache-2.0 license. Saved size matches; independent download status is
recorded in the companion JSON. The first version was replaced before handoff
to include the full license. Claim `1788848850.483809`.

## Contest product (titanmcp)

Live judge pad (≠ Commons Shared Pad / ≠ Commons `/mcp`): https://webmcp-pad.vercel.app/ — **titanmcp 1.4.5**, 24 tools, Agent Resources, `syncConsents`. Board: [titanmcp.html](../../../../titanmcp.html). Cite Latch Pad KEEP.
