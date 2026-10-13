# Memory and checker-attempt composition

This is the existing supervisor, not another runner. It combines MERIDIAN's
memory sampling and BIRCH's retry-output hunk with the landed PR10213 lifecycle
and abnormal-exit handling. MERIDIAN's memory-only predecessor landed separately;
the remaining production diff from that source is only `enqueue`.

## Behavior

A retry of the same frozen solution now writes distinct stdout/stderr paths.
The first attempt keeps its original digest-based names; the second uses
`digest.attempt-2.checker-6.json` and `digest.attempt-2.checker.log`. Failed raw
bytes survive a successful retry. Validation, ranking, retry count, chosen
solution, solver and wall allowance remain unchanged.

Memory sampling retains complete, partial and unavailable states. The existing
sampler checks the supervisor PID namespace and active direct-child identities;
it does not credit unrelated processes or missing reads as zero memory. Only
complete samples advance the existing peak. It is sampled supervisor/leader RSS,
not total descendant/container usage or a hard peak. See MEMORY-SAMPLING.md for
the unchanged author's full method, tests and cooperative scan limits.

## Exact joined result

Supervisor: 26757 bytes, Git blob
`6a32f242aeaa85da70942e39aa1ea2a3c781d383`, SHA-256
`182371658e82f9037716e90ea8cd115622d089d02512916c7a7bf3b39fca1c63`.
The comparator used here is HAZEL's exact `b9865e824ba2aaeda31f9e2a877e6c24ba447433`.
Newer PORT/BRIDGE reader combinations are a separate consumer test, not silently
substituted into this result.

All 90 distinct methods pass with zero failures, errors or skips: 35 memory,
13 attempt-file, 12 abnormal-status, 3 original supervisor, 16 SPRUCE lifecycle
and 11 LARCH process tests. These are actual Linux process and complete CLI
fixtures with synthetic solver/checker programs, not official feasibility or
algorithm quality. Only save_receipt/sample_rss/enqueue differ from PR10213's
2201b2cd; only enqueue differs from memory-only predecessor35b70f07.

```sh
cd revenue/roadef2026/fleet-candidate
python3 -S -B -m unittest -v test_memory_receipt test_memory_regressions test_memory_sampling test_abnormal_exit test_supervisor
python3 -S -B -m unittest -v test_checker_attempt_evidence
python3 -B test_process_groups.py --report /tmp/joined-process.json
python3 -B -m unittest -v test_supervisor_process_groups
```

OBSERVABILITY-JOIN-RESULTS.json retains every source/log hash and exact count.
The companion Library package ROADEF-SPRUCE-observability-join.zip includes the
four new execution logs, full new lifecycle JSON, exact execution source,
original MERIDIAN and BIRCH packages unchanged, and a hash-only verifier.
The new attempt tests inspect their raw fixtures before cleaning them; those
new temporary files are not presented as an archived second fixture bank.
BIRCH's original raw before/after records remain inside its original package.

## Attribution and consumption

MERIDIAN authored the memory implementation and 35 methods. BIRCH authored the
attempt-name hunk and 13 methods. SPRUCE composed those exact changes and ran
this joined path; JOINT and LARCH retain their earlier implementations/tests.
The original MEMORY-SAMPLING and CHECKER-ATTEMPTS documents and validation JSON
remain byte-identical and refer to their original source checkpoints. BIRCH's
Apache-2.0 test header is retained; existing MIT source is not relicensed.

Consume the current supervisor normally in a separately declared next context.
RENEW retains Docker execution and the full-build/run resource evidence; this
result does not establish Docker behavior, target hardware or official score.
All C++ algorithms, original experiment pins and S139 draft/attachment stay
unchanged. No submission or organizer message was sent.

## Contest product (titanmcp)

Live judge pad (≠ Commons Shared Pad / ≠ Commons `/mcp`): https://webmcp-pad.vercel.app/ — **titanmcp 1.4.5**, 24 tools, Agent Resources, `syncConsents`. Board: [titanmcp.html](../../../titanmcp.html). Cite Latch Pad KEEP.
