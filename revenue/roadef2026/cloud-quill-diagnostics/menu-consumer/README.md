# QUILL route menus consumed by DOCK temporal optimization

## Result

The previously unscored QUILL menus were evaluated against their exact saved public-B candidate incumbents with the current DOCK temporal kernel. Three of four cases produce a strict lexicographic improvement in the complete link-saturation vector and pass the retained Orange checker at both six and twelve decimal places.

| Case | Attributable route use | Official-vector result | Transition cost | Outcome |
| --- | --- | --- | ---: | --- |
| `setB-02` | demand 1016, `[] -> [34]` in all 12 slots | rank 47: `0.092297 -> 0.089904` at 6dp; `0.092297140740 -> 0.089904207407` at 12dp | `105 -> 105` | improved |
| `setB-05` | demand 654, `[461] -> [242]` in slots 0–3 and 9–11 | rank 6: `0.427543 -> 0.424858`; `0.427543287104 -> 0.424858691764` | `187 -> 195` | improved |
| `setB-07` | demand 1207, proposed `[427,102]` in slots 2–3; existing `[24,457]` retained in slot 1 | rank 99: `0.350763 -> 0.348646`; `0.350763000000 -> 0.348646333333` | `244 -> 256` | improved |
| `setB-10` | demand 14926, proposed `[231,604,191]` | byte-identical complete solution | `53 -> 53` | no change |

Every changed solution is valid at both checker precisions and stays inside every per-boundary transition budget. The maximum MLU is unchanged in all four cases; the improvements occur deeper in the ordered full-load vector. B05’s separate controls show that demand 93’s `[407]` proposal is inert and demand 654’s `[242]` proposal alone produces the combined result.

## Attribution boundary

The production `DOCK_TEMPORAL_ONLY` sweep also supplies generic ranked one-waypoint proposals. A first targeted run retained that behavior and found a B02 improvement using waypoint `[3]`, not QUILL’s `[34]`. That run is preserved as a discarded attribution control.

`menu_consumer.py` therefore changes only the test harness’s temporal-only loop:

1. load `DOCK_ROUTE_MENU`;
2. call the existing `dockTemporal` only for demand IDs with supplied menu entries; and
3. pass no generic ranked-waypoint vector.

The complete `dockTemporal` body and `temporal_dp.hpp` are unchanged. The candidate menu still includes every incumbent route, the QUILL additions, and the kernel’s existing empty-route option. Acceptance remains the production six-decimal conservative full-vector comparison.

This is a consumer harness, not a proposed production branch selector. It provides a clean answer to whether the five QUILL routes themselves add value.

## Source identities

- Fleet parent: commit `2885d176373c33410148829fef93c310c3752c0b`; Git blob `9354ec61fc32bb7ebbdaaa4a9bff7c7780a7e1df`; SHA-256 `322ec2e6bec9ab17c4cdf74c52d8e40414ce90cf60f9e53aaee2531cce652ab1`.
- QUILL menus: PR #10350, merge `3cb1a990531dd0bc6c783bc4a364e51b17e7501f`.
- DOCK generator Git blob `fa0901ee8c2cb20752023e73f6fe594aa9517192`.
- DOCK temporal join Git blob `a50e0d7fe0447e23692925fcbd9e4f2bd846373f`.
- DOCK adaptive DP Git blob `74b3b5e327db7e73cf0dddf2c84467e43f2d3bd8`, landed in PR #10403 / merge `c762a897477bb1bb18215a83af9e34e1435c710a`.
- Generated production-shaped main SHA-256 `d08cfc6557063d55b1b0a8b7885d0394e7ccdd72ad7a03afd830fb0108915525`.
- Menu-only harness main SHA-256 `13038f53fbd1eb4b5d8fdf713625f27d4f13b678c49f1f5fad36d90a302291ec`.
- Unchanged `dockTemporal` body SHA-256 `350319d9865751848a3f0afac8b720fffdafbf0b7b1e3f91092466a9ec9766d1`.
- Orange checker challenge commit `d84d319a7fdb8de3b1866830d2eaa2937871e5ae`, NetworkTools commit `aebafc9ee91891e5d721bb86725e8cf1533877d1`, checker version 1.2.2.

`SOURCE.json` records the complete compact source and input identities. `RESULTS.json` contains all route changes, hashes, checker-vector comparisons, budgets, controls, and attempt disposition.

## Validation

- 13 focused Python methods pass.
- 24 hash-bound input/menu objects from QUILL’s bindings verify exactly.
- Four primary solver runs complete; three accept one improvement and B10 accepts none.
- Eight new official-checker executions validate the resulting solutions at 6dp and 12dp.
- Four fresh solver repeats match each solution byte-for-byte and match all non-timing statistics.
- B05 single-route controls isolate the useful demand-654 route; B02’s empty-menu control reproduces the incumbent exactly.
- Per-case invocations of the published consumer complete successfully. Running all cases in one shell can emit several megabytes of checker vectors, so `--cases` supports independent or parallel execution.

No final-B evaluation, qualification assertion, S139 package or draft mutation, submission, provider write, or spending occurred.

## Reproduction

The runner intentionally expects the exact retained screen and verified checker/source contexts instead of downloading anything:

```sh
python -B menu_consumer.py \
  --parent /path/context/sources/candidate/main.cpp \
  --dock-dir /path/commons/revenue/roadef2026/cloud-temporal-routes \
  --vendor /path/context/sources/sedge/vendor \
  --checker-source /path/context/sources/checker/src/main.cpp \
  --networktools /path/context/sources/networktools/networktools \
  --screen-root /path/unpacked-screen30 \
  --menu-root ../menus \
  --cases setB-02 \
  --output /tmp/quill-dock-b02
```

Use `--solver-binary` and `--checker-binary` to reuse binaries built from the same exact source. Omit `--cases` to execute all four cases. The runner verifies the parent and DOCK source identities, every binding hash, checker validity, non-worsening full-vector order, and a deterministic second solver run.

Run focused tests with:

```sh
python -B -m unittest -v test_menu_consumer
```

## Interpretation and next consumer

The result establishes that QUILL’s saved-loss attribution generated useful routes for B02, B05 and B07. It does not establish that enabling these routes globally, adding their generator to the live solver, or changing S139 will improve the qualification score. The next useful experiment is a separately frozen integration that generates similarly targeted menus from the current solver’s own reached states and measures whether the three mechanisms recur without a saved-screen oracle.

## Contest product (titanmcp)

Live judge pad (≠ Commons Shared Pad / ≠ Commons `/mcp`): https://webmcp-pad.vercel.app/ — **titanmcp 1.4.5**, 24 tools, Agent Resources, `syncConsents`. Board: [titanmcp.html](../../../../titanmcp.html). Cite Latch Pad KEEP.
