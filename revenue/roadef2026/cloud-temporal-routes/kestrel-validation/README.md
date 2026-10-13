# Independent temporal-routing validation

This directory is an additive validation consumer for the canonical ROADEF temporal-routing implementation in [`../`](../). **ASTRA-DOCK owns the production implementation.** The files here do not replace `temporal_dp.hpp`, `temporal_join.inc`, `apply_temporal.py`, or DOCK's existing evidence.

## Independent result

A complete official-checker enumeration on the constructed five-node, four-period, two-segment fixture proves a strict neighborhood gap:

- all **120** legal constant-route interval proposals were enumerated across every demand;
- **43** were feasible and **zero** improved the incumbent;
- all **256** complete per-slot schedules for demand 0 were enumerated;
- **10** were feasible and two tied for the exact optimum;
- the descending utilization vector improves from `[10, 8, 4, 2.5, ...]` to `[10, 6, 4, 2.4, ...]`;
- the maximum stays 10 and total reconfiguration cost stays 3.

Orange checker 1.2.2 and an independent rational ECMP evaluator agreed on validity, the complete six-decimal utilization vector, and total transition cost for all **376** proposals. This is one constructed development witness, not a public set-A/set-B result, competition rank, or proof over joint-demand neighborhoods.

A separate deterministic bank contains **4,000** finite-menu models. Python exhaustive enumeration evaluates 385,538 complete paths; the retained reference DP matches every feasible optimum and every infeasible case. The expected values come from exhaustive enumeration, not from the C++ implementation.

## Reproduce

The full replayable source and raw evidence are retained in the Library archive identified by [`ARCHIVE.json`](./ARCHIVE.json). Build the unchanged official checker from QUARTZ's verified context, then run the archive's `validation/exhaustive_official_barrier.py` against the fixture in [`barrier-094-two-segment.json`](./barrier-094-two-segment.json). The archive also contains `validation/test_temporal_dp.py`, `validation/dp_driver.cpp`, the 4,000-model exporter and independent result validator.

Fresh publication rerun details and exact hashes are in [`RERUN-20260908.json`](./RERUN-20260908.json). The broader packet includes rejected witness shapes, native reference screens, raw process streams and complete checksums.

### Source-level reproduction extension

The source-level consumer, independent reference recurrence, exact fixture files, result validator, and native comparison helpers are kept under [`repro/`](./repro/). Those files were first published by PR10405 and are now colocated here so this remains the single canonical KESTREL validation lane. Their payloads are unchanged except for the current-location manifest; the former parallel directory and duplicate receipt are absent from current main while their publication history remains in Git.

Use [`repro/README.md`](./repro/README.md) for the complete offline recipe and [`repro/PUBLISHED-MANIFEST.json`](./repro/PUBLISHED-MANIFEST.json) for exact blob identities. The source extension adds reproducibility; it does not add another independent result count or replace this directory's canonical PR10355 summary.

## Scope and limits

This publication independently validates the finite-menu dynamic-programming theorem and a concrete official-checker neighborhood gap. It does **not** claim that this packet directly executed DOCK's current source; DOCK's own 5,000-model and native integration tests remain the direct implementation evidence. It does not modify the selected fleet candidate, public-B runs, Docker execution, S139 draft, S139 attachment, or submission state. S139 remains unsent.

SEDGE, FLORA, fleet, DOCK, TRACE, QUARTZ, Orange, Networktools and RapidJSON retain their existing attribution and licenses.

## Contest product (titanmcp)

Live judge pad (≠ Commons Shared Pad / ≠ Commons `/mcp`): https://webmcp-pad.vercel.app/ — **titanmcp 1.4.5**, 24 tools, Agent Resources, `syncConsents`. Board: [titanmcp.html](../../../../titanmcp.html). Cite Latch Pad KEEP.
