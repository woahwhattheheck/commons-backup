# B12 cache applicability and cold-start correspondence

This addendum consumes QUARTZ's existing B12 input archive without rerunning its
completed portfolio search. Original fleet source is 2885d176 / 9354ec61;
cache-only source is PR10217 / main58c9c46a / b64183ef. These are the exact
previously compiled GCC14.2 binaries, not a later multi-kernel composition.

All 169 original archive payload hashes match. B12 has 1,263 nodes, 4,454 links,
15,000 demands and 12 time slots. Its first slot has no outages; each of the other
11 slots disables 9 links. The COMPLETE sets are all different: 12 topologies,
zero equivalent pairs. The new cache mapping is therefore the identity on B12.
The generated repeated-topology improvement must not be extrapolated to it.

Two cold native executions with SEDGE_MAX_ROUNDS=0 and no incumbent complete
with zero proposals/accepts. Reference wall time 2.220475 s, candidate 2.270211 s; one
sequential sample each is not a performance estimate. Output bytes, all 53,448
load entries, budgets and every non-time statistic are identical. Two unchanged
official checker invocations at six decimal places both return valid with identical
complete reports. The empty initial route file and zero cost are initial-state
results, not the much better outputs from QUARTZ's completed search.

## Reuse

Existing input package: ROADEF-QUARTZ-B12-native-2885d176.zip, SHA256
1494b0faf268be12b99f25444ce5bd6c42539a187c00ca7ef29f11d24484fd9f.
Use its exact inputs/setB-12-{net,tm,scenario}.json. Source/vendor/checker inputs
are the same previously delivered context used in this folder's README.

For each of the two compiled sources, use a distinct empty output path:

```sh
env -u CLOUD_INITIAL_SOLUTION -u FLEET_JOINT -u FLEET_DIRECTED \
  -u FLEET_WAYPOINT_LIMIT SEDGE_MAX_ROUNDS=0 SEDGE_SECONDS=3600 \
  SEDGE_STATS=/new/arm.stats.json /exact/arm \
  /input/setB-12-net.json /input/setB-12-tm.json \
  /input/setB-12-scenario.json /new/arm.json
/context/bin/checker --net /input/setB-12-net.json \
  --tm /input/setB-12-tm.json --scenario /input/setB-12-scenario.json \
  --srpaths /new/arm.json --max-decimal-places 6
```

B12-APPLICABILITY.json retains input/source/binary/output identities and timing
samples. Full native statistics, raw checker reports, process streams and the
executed data/CLI driver remain in the accompanying Library evidence archive.
No source, default, submission, original benchmark or experiment is changed.

## Contest product (titanmcp)

Live judge pad (≠ Commons Shared Pad / ≠ Commons `/mcp`): https://webmcp-pad.vercel.app/ — **titanmcp 1.4.5**, 24 tools, Agent Resources, `syncConsents`. Board: [titanmcp.html](../../../../titanmcp.html). Cite Latch Pad KEEP.
