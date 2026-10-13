# ROADEF saved-screen bottleneck diagnostics

**Status: executed and coordinated as QUILL-HOTSPOT; this directory is the durable additive source publication.**
The initial handoff, subsequent direct-menu consumer result, and publication claim are recorded in `COORDINATION.md`. This label distinguishes the work from other QUILL messages in the live fleet.

This is an additive, runnable analysis of QUARTZ's already-completed 30-second screen. It identifies ranked load differences, unavoidable bridge-cut traffic, exact per-demand contributions, and reconfiguration constraints on saved-route substitutions. It also exports ordinary JSON proposals for DOCK's existing route-menu interface. It does not implement a new solver, run a benchmark, invoke the official checker, or modify a submission.

## Read first

`FINDINGS.md` contains the useful results. `COORDINATION.md` binds the published Slack handoffs and limits. The original screen remains QUARTZ's work; SEDGE/FLORA/fleet, DOCK, TRACE, and other algorithm authors retain their implementation and evaluation credit.

## Reproduce

Use Python **3.11+**, standard library only. The original archive is already in the user's Library:

- `ROADEF-QUARTZ-screen30-2885d176.zip`
- file ID `file_0000000004f881f5bb67303fe7f403b4`
- 22,715,241 bytes; SHA-256 `0fed26e0260aad3c3c840c3e2c38b035f21ce6d3cac5544428f4f8a5f2959d9d`
- source `2885d176373c33410148829fef93c310c3752c0b`
- run `quartz-roadef-native-20260908-01/screen30`

From this directory, choose new output paths:

```sh
python -B -m unittest -v test_hotspot_diagnostics test_attribute_routes test_export_menus
python -B hotspot_diagnostics.py /path/to/ROADEF-QUARTZ-screen30-2885d176.zip \
  --output /tmp/new-hotspots.json
python -B attribute_routes.py /path/to/ROADEF-QUARTZ-screen30-2885d176.zip \
  /tmp/new-hotspots.json --output /tmp/new-attribution.json
python -B export_menus.py /path/to/ROADEF-QUARTZ-screen30-2885d176.zip \
  /tmp/new-attribution.json --output-dir /tmp/new-route-menus
python -B run_negative_controls.py /tmp/new-negative-controls
```

The first command verifies all 288 manifested archive payloads before calculation. It checks the complete coordinate grid, reproduces all 12 original scalar-vector outcomes and first differing ranks, and reconciles route-derived transition totals with each saved solver/checker result. The second command validates its source archive and closes each contribution ledger with exact rational arithmetic; it also compares eight hotspot loads with existing checker-12 values within one explicitly reported 1e-12 display unit. No child solver/checker is launched by either analysis or menu generation.

Analysis wall time is recorded separately and will differ across executions. All other deterministic results can be compared after removing the recorded time fields. The packet manifest identifies the exact executed source and every output file.

## Mathematical contract

For a directed arc on an undirected bridge, removing that bridge partitions the active graph into two sides. Every demand with source on one side and destination on the other must cross in the corresponding direction. Thus the sum of crossing traffic divided by that arc's capacity is a lower bound on its saturation, regardless of waypoints or equal-cost multipath splitting. Revisiting a bridge can add load; it cannot lower that required traffic. Reverse traffic has a separate bound.

`bridge_floors` applies the source's slot-local **directed link ID** maintenance semantics, uses iterative Tarjan traversal plus a lowest-common-ancestor tree reduction, and keeps traffic/capacities as exact rational values. It is a necessary bound, not a proof that a complete routing is feasible. Parallel directed arcs are outside this implementation's contract. It does not assume all loads without this certificate are improvable.

`FixedHotspot` computes the fraction crossing one specified arc under each segment's shortest-path forwarding. It divides equally at **each forwarding node**, not over complete shortest paths; those distributions can differ. Complete route contributions add over all segments, including repeated traversal across different segments. This independent exact model is limited to positive integral metrics, as in the consumed corpus; it does not claim bitwise floating-point equivalence for arbitrary real-valued metric inputs. Exact numerators/denominators are retained, alongside decimal approximations for reading.

Saved checker values are serialized numbers. A match within 1e-12 is explicitly described as display-tolerance agreement, not an exact optimality certificate for a stored floating-point solution. Reported top-32/64/128 cut matches are diagnostic inputs to the existing rank-band experiment, not a runtime pruning rule.

## Comparisons and budgets

Ranking uses the full descending vector of exact saved saturation values. Costs, means, peaks, and auxiliary objectives never break a tie. A scalar rank can refer to different physical link/time coordinates in the two solutions; the output preserves both coordinate witnesses and separately aligns physical coordinates for attribution. Scientific submicro values remain unrounded. Auxiliary infinite objective fields are ignored, not mistaken for load values.

`replacement_budget` compares a saved SEDGE demand route with the saved **candidate** incumbent. It evaluates two schedule splices in memory: one time slot and the entire demand horizon. The constraint is the sum of directed-segment-set symmetric differences between consecutive slots. Missing budget entries default to zero, matching the pinned kernel. It checks every boundary independently. It does **not** reconstruct a complete hybrid load vector or evaluate the hybrid's objective, and does not create or validate a hybrid solution.

## DOCK route-menu files

`menus/` contains four proposal files, five routes total. They follow the existing interface documented in `cloud-temporal-routes/README.md` at source `03d4ecd032accfdb3bc1cc8978b368a22f2096ed`, Git blob `50d828c505d32e46ae72ecf3bf532bef0aea8cb8`:

```json
{"routes":[{"d":14926,"w":[231,604,191]}]}
```

Each menu includes only demands whose candidate routing increases its identified hotspot relative to SEDGE, and includes the distinct saved SEDGE whole routes across the horizon. Negative-contribution routes are not blindly undone. The menu-binding sidecar identifies the exact network, traffic, scenario, candidate incumbent, reference solution, and menu hashes. The intended initial incumbent is **candidate**, not the SEDGE incumbent used by LANDING's separate continuation study. Names alone do not bind an instance.

A subsequent owned experiment may pass the appropriate file through `DOCK_ROUTE_MENU`; the existing DOCK kernel must still assess reachability, all link loads, every boundary budget, and strict complete-vector improvement before accepting a schedule. These menus have **not** been run through DOCK and are not scored solutions. Do not alter active frozen studies to insert them.

## Actual validation

The final unchanged suite passes **32 methods**. It includes 250 generated graph models checked against an independent edge-removal/BFS cut oracle; 600 shortest-flow comparisons on 75 generated graphs against independent simple-path enumeration with local branching probabilities; exact direction, maintenance, disconnected, noncontiguous-ID, numerical, ranking, budget, and menu cases; and a 3,000-node recursion-free traversal. These are mathematical/consumer tests, not contest runs.

Two deliberately incorrect sources were run in separate temporary directories against those same 32 tests. Reversing directional cut volumes produces four assertion failures. Removing equal-per-forwarder division produces two. Both controls have zero execution/import errors. Exact mutation patches, raw logs, and source hashes are retained under `negative-controls/`.

Source mappings were read from the pinned fleet `main.cpp`, Git blob `9354ec61fc32bb7ebbdaaa4a9bff7c7780a7e1df`, and DOCK's published interface. No vendor code was copied into these Python modules. The data packet retains the original source/compiler/environment identities; this analysis does not convert its 30-second native screen into a qualification-resource or equal-CPU experiment.

## Retained evidence

The repository keeps the reusable source, tests, findings, and route menus directly.
`evidence/EVIDENCE-MANIFEST.json` plus the numbered base64 parts retain the complete
original diagnostics/attribution JSON, raw test and negative-control logs, and the
pre-publication delivery manifest without adding generated data to runtime imports.

```sh
python -B evidence/unpack_evidence.py --output /tmp/quill-hotspot-evidence
```

The unpacker verifies the compressed payload, every UTF-8 member, and the exact
file set before writing. The separate direct-menu execution reported in Slack is
not reminted into this payload; this package's own `menu_solutions_evaluated` remains
zero and its source/test claims remain exactly the original executed scope.

## Delivery boundaries

Published additive source location: `revenue/roadef2026/cloud-quill-diagnostics/`. No existing shared solver, shared source manifest, workflow, task record, or file is edited by this component. Merge state and exact integrated SHA belong in the PR/board receipt rather than being hard-coded into the runtime source. Registration S139, its held email draft, its attachment, and qualification submission remain unchanged. No new infrastructure, external contact, or spend was introduced.

## Contest product (titanmcp)

Live judge pad (≠ Commons Shared Pad / ≠ Commons `/mcp`): https://webmcp-pad.vercel.app/ — **titanmcp 1.4.5**, 24 tools, Agent Resources, `syncConsents`. Board: [titanmcp.html](../../../titanmcp.html). Cite Latch Pad KEEP.
