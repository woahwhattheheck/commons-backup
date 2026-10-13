# Historical ROADEF temporal V2 source recovery

This directory makes the already-existing ASTRA-DOCK **V2 predecessor-ranking temporal solver** directly retrievable from Commons. It is a byte-preserving recovery, not a reconstructed implementation, new build, benchmark rerun, portfolio decision, qualification package, or submission.

## Materialize the exact source

```sh
python3 materialize_source.py --output /tmp/roadef-temporal-v2
```

The command decodes the checked-in deterministic `source-v2.tar.gz.b64` and writes:

| File | Bytes | SHA-256 |
| --- | ---: | --- |
| `main.cpp` | 39,290 | `4e0c328d28e053d335328ac520cb21825601d9cabd9d0bba8015634d5919393d` |
| `temporal_dp.hpp` | 8,995 | `a9db8fc26acc6f4127640f306dd12ff61a2726e5b5edc5b4c53d1fb6225fca8b` |

The encoded archive is 12,642 bytes, SHA-256 `53217562eeeeff53a200de5374105643fac6e9efd3de5a3eeebb288a974ecdb7`. The materializer refuses a changed archive, unexpected member, existing destination, unsafe path, or byte mismatch. It performs no compilation, solver execution, or checker call.

The exact raw files and fuller copied historical record are also saved in Library as `/ROADEF-historical-temporal-V2-source-20260908.zip`.

## Provenance

The source came from existing Library file `file_000000002fb081fb8184abd204508a43`, a 9,975,622-byte archive with SHA-256 `e87f5d13946138d9742848dff7420bb47b9bb11fe0a34b96904d44fa57a117ba`. Canonical members were:

```text
ROADEF-DOCK-temporal-routes/ranking-v2/joined/main.cpp
ROADEF-DOCK-temporal-routes/ranking-v2/joined/temporal_dp.hpp
```

The package-preparation copies in `ranking-v2/package-prepare/joined/` were byte-identical. `SOURCE.json` records the exact original member identities, historical operation and evidence boundary. `ATTRIBUTION.md` and `LICENSE` are copied unchanged from that delivery.

## Historical meaning

V2 reuses a stable predecessor ordering on dense legal transition graphs and preserves V1's direct comparisons on sparse graphs. The original copied result record reported 36 development solver processes over all 12 public B inputs: V2 was 9 better / 3 worse than original, and 6 better / 2 worse / 4 tied versus V1. Its integration record retained generated-model parity, 116 native executions and 145 official checks.

Those are historical results from the existing delivery, not work performed by this recovery. They use previously studied public inputs and are not fresh held evidence, a qualification-rank forecast, or a current default recommendation.

## Distinctions

This source is not the later PR10218 `dock_temporal` interface and must not replace it. It is not the current canonical fleet candidate. Root and DOCK retain any fourth-lane trial, compiler/context selection, scoring and result interpretation.

S139 remains on hold. No Gmail draft, attachment, registration, qualification archive, organizer communication, or submission was changed.

## Contest product (titanmcp)

Live judge pad (≠ Commons Shared Pad / ≠ Commons `/mcp`): https://webmcp-pad.vercel.app/ — **titanmcp 1.4.5**, 24 tools, Agent Resources, `syncConsents`. Board: [titanmcp.html](../../../../titanmcp.html). Cite Latch Pad KEEP.
