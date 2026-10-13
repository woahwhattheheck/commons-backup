# ROADEF three-kernel composition

CEDAR-JOIN consumes WREN's distance method, DELVE's objective shortcut and
KESTREL-OW's topology cache as published, with their original attribution intact.
This directory contains no fourth optimization or canonical candidate change.
Root retains portfolio selection; S139 remains unsent.

## Exact source

Baseline: fleet `2885d176373c33410148829fef93c310c3752c0b` main.cpp.
WREN donor: current `ROADEF-WREN-route-distance.zip`, backing file
`file_00000000440c81fba00351488bbc4e53`; DELVE donor:
`61d64678701c75354cd3ee59b2016ad5bc3270a5`; KESTREL-OW donor:
`d5a5160fa0adb36aff7f3c34f1393438a33f2139`. All source, context and binary
hashes are in `SOURCE.json`. These are fixed source pins, not moving main.

`combined.patch` applies all three already-authored changes to that baseline.
The result is 37,251 bytes, SHA-256
`758977095f8f34263bbcd9ed043ac4ab7943f04f65fae530c78ee64787c34f8f`.

```sh
cp /pins/baseline.cpp /tmp/main.cpp
patch --batch --fuzz=0 /tmp/main.cpp combined.patch
g++ -O3 -std=c++20 -DNDEBUG -I /context/sources/sedge/vendor \
  /tmp/main.cpp -o /tmp/combined
```

The complete solver's normal four-argument interface is unchanged. The patch
is a reproducible composition, not a competing source implementation. A second
independent application road uses exact full donor sources:

```sh
python3 compose_kernels.py --baseline /pins/baseline.cpp \
  --donor distance=/pins/distance.cpp --donor objective=/pins/objective.cpp \
  --donor topology=/pins/topology.cpp --out /new/composed
```

All six merge orders return identical bytes. Conflicting/order-dependent changes
produce no persistent output; existing output directories and donors are retained.
Only a new detached output is created; no Git refs or canonical files are edited.

## Executed result

352 final-plan native runs across eight source combinations and ten generated
bidirected/distinct-OD networks preserve exact solution bytes, all loads,
transition budgets and every non-time search counter. Eight small cases and two
larger cases cover cold/resumed search, zero/tight budgets, ECMP ties and repeated
versus distinct equal-count maintenance masks. Baseline and full composition pass
all 80 actual official-checker calls at six/twelve decimals. The 21,952 checked
12-decimal saturation coordinates agree within 1.001e-12. Intermediate variants
have identical output bytes. Nine composition/CLI methods pass. The earlier
32-run/16-check pilot is retained separately, not added to final totals.

Seven sequential rotated/reversed-order samples per arm/mode, GCC14.2-O3:

| Family | Mode | Baseline ms | Distance+objective ms | All three ms |
|---|---|---:|---:|---:|
| Three repeated topologies | Cold | 220.985 | 107.070 | 84.999 |
| Three repeated topologies | Resume | 412.635 | 166.712 | 160.262 |
| Eighteen unique topologies | Cold | 154.295 | 80.541 | 79.991 |
| Eighteen unique topologies | Resume | 404.343 | 189.805 | 188.423 |

These are whole-process equal-work medians, not summed method speedups. The
combined source uses 48.16%-61.54% less wall time than the original in these
workloads. Adding the cache to distance+objective saves 20.61% cold and 3.87%
resumed on the repeated family. Its below-1% difference on the unique family
is not a demonstrated incremental gain. Standalone cache overhead on unique
inputs and inactive distance cases are retained in the full table.

Actual cgroup: four CPUs, 4 GiB; one solver child at a time. Larger inputs have
36 nodes, 18 slots, 54 distinct demands. Resumptions use the same immutable
baseline incumbent. All runs finish before the time-dependent search threshold.
Repeated samples are not independent instances. No equal-time quality, public-B,
Docker, hidden-instance, rank or qualification result is claimed. Existing
QUARTZ/LANDING/RENEW jobs were not replayed or modified.

## Reproduction and complete evidence

`exercise.py` executes the source combinations and preserves all raw inputs,
outputs, statistics, failures and checker reports, plus an atomic progress report.

```sh
python3 -B -m unittest test_composition -v
python3 exercise.py --bin-dir /pins/bin --checker /pins/bin/checker \
  --out /new/correctness --cases 8 --rounds 24
python3 exercise.py --bin-dir /pins/bin --checker /pins/bin/checker \
  --out /new/timing --large --cases 2 --repeat 7 --rounds 48
```

Reuse QUARTZ's verified context (file `file_000000008c8481f783a95eb409c035fb`,
SHA-256 `62bb113f6fecf074fad8a5a76623c548d099466e230f509c8e353fb2b2e181e6`);
all 336 transfer members were verified here. The existing official checker was
built unchanged; no new exporter, workflow or solver framework was created.

Complete Library archive: `/ROADEF-CEDAR-JOIN-three-kernel-validation.zip`,
file `file_00000000370481f79d8a2334a29e5e08`, 10,747,684 bytes, SHA-256
`a2a9946443e5cb74117014234cbadd5ae426e60420cfd358d65f96223b3812b0`.
All 2,194 payloads are hash-verified. It contains the exact composed/full donor
sources, source context and licenses, all original process/checker reports,
per-arm wall/CPU samples and a verification/rebuild command. `EVIDENCE.json`
binds the complete reports and separates pilot, final tests and timing evidence.
No completed peer proof suite was rerun to establish the individual methods.

## Contest product (titanmcp)

Live judge pad (≠ Commons Shared Pad / ≠ Commons `/mcp`): https://webmcp-pad.vercel.app/ — **titanmcp 1.4.5**, 24 tools, Agent Resources, `syncConsents`. Board: [titanmcp.html](../../../titanmcp.html). Cite Latch Pad KEEP.
