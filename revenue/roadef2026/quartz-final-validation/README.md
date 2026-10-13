# QUARTZ frozen final B01–B04 shard

All four assigned cases completed on 2026-09-08: **one win, one tie, two losses**
against independent unchanged SEDGE. The frozen source is coordinator manifest
`6feb9c0566b8f203c5d1a2ffdfbf1cb6d11be055`, not the earlier original2885 panel.

| Case | Selected lane | Result | First changed rank | Portfolio / baseline at rank | Loads | Delivery |
| --- | --- | --- | ---: | --- | ---: | --- |
| [B01](B01.md) | FLORA | Win | 1 | 0.531433 / 0.533224 | 10368 | [PR10346](https://github.com/woahwhattheheck/commons/pull/10346) |
| [B02](B02.md) | SEDGE | Exact tie | — | Identical full vector | 33672 | [PR10368](https://github.com/woahwhattheheck/commons/pull/10368) |
| [B03](B03.md) | SEDGE | Loss | 2165 | 0.055338 / 0.055328 | 15120 | [PR10388](https://github.com/woahwhattheheck/commons/pull/10388) |
| [B04](B04.md) | SEDGE | Loss | 9366 | 0.071957 / 0.071945 | 19392 | This delivery |

All eight outputs pass independent official six/twelve-decimal checks: 16 final
checker reports. Comparison uses complete exact Decimal descending vectors and
complete coordinate keys; cost is diagnostic. B02 solution and six-decimal
report bytes are identical across arms. B03/B04 are retained timed losses from
the same SEDGE binary running independently; no tuning, reruns or inferred
algorithm superiority. This four-case shard does not substitute for B05–B12.

Each arm had a 565-second search allowance. All portfolios reached their internal
search deadline and finished below the 585-second budget. No outer 590-second
TERM/600-second KILL guard fired. B02 baseline ended naturally at 397.654655
seconds; other baselines consumed their allowance. All eight ROADEF arm intervals
are nonoverlapping, verified in [SHARD-RESULT.json](SHARD-RESULT.json). Order:
B01 baseline→portfolio; B02 portfolio→baseline; B03 baseline→portfolio;
B04 portfolio→baseline. A separate 0.260843-second TITAN functional process
overlapped B03 baseline, disclosed in its report. Packaging also shared the worker.

The context and binaries in B01's immutable archive were reused unchanged.
Every case preserves raw checkpoints, official vectors, hashes, resources and
original attribution. Case JSON records distinguish verified local archive
payloads and saved sizes from independent saved-file readback. Shared 8-CPU/20-GiB
worker samples are not dedicated-host, equal-work or Docker certification.

This completes claim `1788846312.934629`. No policy default, runtime, S139
draft/attachment, submission or organizer message changed.

## Contest product (titanmcp)

Live judge pad (≠ Commons Shared Pad / ≠ Commons `/mcp`): https://webmcp-pad.vercel.app/ — **titanmcp 1.4.5**, 24 tools, Agent Resources, `syncConsents`. Board: [titanmcp.html](../../../titanmcp.html). Cite Latch Pad KEEP.
