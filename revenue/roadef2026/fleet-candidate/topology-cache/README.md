# Maintenance-equivalent topology caches

`main.cpp` now shares shortest-path DAGs and ECMP segment fractions between time
slots with exactly equal complete offline-link masks. Every slot keeps its own
traffic, incumbent routes, loads, route-change budgets and search state. The
original routing arithmetic, candidate ranking, move acceptance, cache limit and
random generator are unchanged.

## Why reuse preserves a segment

Within one Solver, directed edges, metrics and capacities are immutable. A DAG
for a target depends only on those edges and the offline mask. Equal complete
masks therefore produce the same distances, forwarding edges and order. Given
that DAG and the same source/target, the existing node-by-node ECMP computation
produces the same sparse coefficients. `topologySlot[t]` selects the earliest
identical mask after all interventions are parsed; no time-dependent traffic
quantity enters either shared cache.

Initialization compares whole masks, not outage counts or only one machine word.
Nonconsecutive equivalent slots share data; distinct masks never alias. The
mapping costs O(h^2) complete-mask comparisons in the worst case and a small
additional vector lookup on cache access. No improvement is promised when every
slot has a unique topology.

## Executed evidence

Reference: commit `2885d176373c33410148829fef93c310c3752c0b`, source blob
`9354ec61fc32bb7ebbdaaa4a9bff7c7780a7e1df`, SHA256
`322ec2e6bec9ab17c4cdf74c52d8e40414ce90cf60f9e53aaee2531cce652ab1`.
Candidate source blob `b64183efd119841865dffb51f6dc65d17d50116f`, SHA256
`a3bf3968145cd6dc2431ad34720c634395e326f7425e56f2cdbc3d4c2b4fa905`.
The reference was also read unchanged at publication base
`439e73a8428caa9425e60f9ac300dcf33a9a6f8a`. Original SEDGE/FLORA and fleet
implementation attribution is retained.

GCC 14.2 compiled the actual reference and candidate. The probe changes member
visibility and the CLI symbol only in a separate test translation unit; all
production method bodies execute as supplied.

- 10,393 exact segment queries on 11 generated graphs match bit-for-bit, including
  repeated/nonconsecutive maintenance, distinct equal-count outages, mask bits
  beyond 64, disconnected destinations, a single slot and varying traffic.
- 22 complete solver pairs (0 and 8 rounds per graph) have identical serialized
  solutions and every statistics field except elapsed time.
- Three deliberate mistakes are detected: grouping outage counts, comparing only
  the first 64 links, and retaining per-time segment keys. The last is a reuse
  regression with unchanged flows, not a false routing failure.
- Forced eviction every 17 queries preserves all 1,728 exact flows in each arm.
- 14 additional full-solver timing pairs use two 40-node, 24-slot, 12-round
  workloads. Every solution, load, budget and search counter matches.
- The unchanged official checker accepts both arms on 10 separately normalized
  generated instances, with identical full reports (20 checker calls). The
  normalization consistently relabels nodes/links/waypoints to contiguous IDs,
  adds `directed`, and omits empty no-op intervention rows. Raw noncontiguous-ID
  native tests remain separate. The first raw-label adapter attempt and its
  checker failure are retained in the complete evidence, not counted as passes.

## Measured timing and size

Cache-heavy 60-node/24-slot all-pairs workload, five alternating-process pairs:
three distinct masks reduce allocated DAGs 1440 to 180 and cached segments
86400 to 10800. Median whole-process time is 158.829 to 49.148 ms. In the
all-unique-mask control it is 153.473 to 166.388 ms; that slower sample is retained.

Actual complete 12-round solver, seven alternating-process pairs per workload:
repeated masks give median 119.729 to 90.765 ms (24.2% less); unique masks give
106.614 to 106.829 ms. Both arms perform the same 982 attempts, 12 accepts and
646 ranked candidates on each of these generated workloads. These are local
native process measurements, not method-only timings, public-instance scores,
full-budget tests, Docker evidence or qualification results. Real time-limited
search may reach different neighborhoods because it can perform more work.

`RESULTS.json` retains all samples, structural counts, source identities and
checker-result hashes. Full generated inputs, outputs, build logs, mutation
controls and earlier attempts are retained in the accompanying Library bundle.

## Reproduce offline

Use the existing source intake for the unchanged reference plus RapidJSON:
Library `ROADEF-KESTREL-fleet-source-2885d176.zip`, SHA256
`75ac5dbd517196d01e73dacd9c1d26d2cabce04e3232084ffa7b34ab4fbfb98a`.
TRACE's canonical source handoff provides the same original file. The separate
QUARTZ context ZIP, SHA256
`62bb113f6fecf074fad8a5a76623c548d099466e230f509c8e353fb2b2e181e6`,
contains the unchanged official checker and its dependencies; all 336 payload
manifest entries were checked here. No source export or download job is needed.

From this folder, with absolute paths to extracted inputs:

```sh
python check_topology_cache.py --reference /input/main.cpp --candidate ../main.cpp \
  --vendor /input/vendor --output /tmp/topology-check
python check_controls.py --reference /input/main.cpp --candidate ../main.cpp \
  --vendor /input/vendor --checks /tmp/topology-check --output /tmp/topology-controls
python check_official.py --checker /context/bin/checker \
  --checks /tmp/topology-check --output /tmp/topology-official
```

The checker can be built from QUARTZ's existing context without rerunning other
solver builds: `g++ -O3 -std=c++20 -DNDEBUG -DLANG_EN
-Isources/networktools/networktools sources/checker/src/main.cpp -o bin/checker`.

Only cache initialization/indexing, the main.cpp manifest entry, and this
regression/evidence directory change. WREN's distance and DELVE's comparison
work remain distinct. Existing frozen native/container benchmarks, S139 draft,
attachment and submission state are unchanged.

## Contest product (titanmcp)

Live judge pad (≠ Commons Shared Pad / ≠ Commons `/mcp`): https://webmcp-pad.vercel.app/ — **titanmcp 1.4.5**, 24 tools, Agent Resources, `syncConsents`. Board: [titanmcp.html](../../../../titanmcp.html). Cite Latch Pad KEEP.
