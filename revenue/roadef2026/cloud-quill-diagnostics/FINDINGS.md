# Saved-screen findings — QUILL-HOTSPOT

## Decision-useful result

**The original candidate loses six of twelve instances, and every loss is below the maximum-load rank.** The new diagnosis distinguishes high loads required by bridge cuts from specific demand routes that create avoidable-looking local concentration. It supplies concrete proposals for the existing temporal and critical-rank work, not another benchmark or a claim that an untested hybrid wins.

All findings below use QUARTZ's unchanged 30-second screen, archive SHA-256 `0fed26e0260aad3c3c840c3e2c38b035f21ce6d3cac5544428f4f8a5f2959d9d`, source `2885d176373c33410148829fef93c310c3752c0b`. The six wins/six losses are the original result, independently read and reproduced here. **This continuation ran zero solvers and zero new official-checker calls.**

## Full-vector result and cut-bound evidence

A smaller value at the first differing descending rank wins. “Prefix at cut” counts candidate coordinates in the equal scalar prefix whose saved 12-decimal value is within 1e-12 of an exact bridge-cut lower bound. “Top 32 at cut” uses the same criterion. This is tolerance-limited agreement, not permission to prune those coordinates in a live solver.

| Instance | Candidate vs SEDGE | First rank | Candidate | SEDGE | Equal-prefix coordinates at cut | Top 32 at cut |
|---|---|---:|---:|---:|---:|---:|
| B-01 | win | 1 | 0.53481 | 0.534967 | 0/0 | 0/32 |
| B-02 | loss | 47 | 0.092297 | 0.089904 | 44/46 | 31/32 |
| B-03 | loss | 1012 | 0.078856 | 0.078837 | 439/1011 | 28/32 |
| B-04 | win | 1 | 0.6694 | 0.669499 | 0/0 | 0/32 |
| B-05 | loss | 6 | 0.427543 | 0.425636 | 0/5 | 0/32 |
| B-06 | win | 238 | 0.120928 | 0.121291 | 211/237 | 32/32 |
| B-07 | loss | 2 | 0.554801 | 0.543582 | 0/1 | 0/32 |
| B-08 | win | 430 | 0.004928 | 0.004941 | 286/429 | 31/32 |
| B-09 | win | 749 | 0.00492 | 0.004923 | 406/748 | 32/32 |
| B-10 | loss | 5 | 0.869291 | 0.807464 | 4/4 | 18/32 |
| B-11 | win | 3 | 0.349811 | 0.362711 | 0/2 | 0/32 |
| B-12 | loss | 18 | 0.46358 | 0.445406 | 0/17 | 0/32 |

**B06 and B09 have all 32 initially highest coordinates at bridge-cut lower bounds within display precision.** B02 has 31 of 32, and 44 of its 46 equal-prefix coordinates meet those bounds. This is concrete input for TRACE's separately owned rank-band experiment: a high-load-only search can focus on a largely bound-attained prefix while useful scalar ranks lie below it. It does not establish that the top-32 choice caused the recorded solver's termination or that widening it will win.

The certificate is simple: every demand crossing a bridge cut must traverse its corresponding directed arc, so required crossing traffic/capacity lower-bounds that arc's load. Direction, time-slot maintenance, and exact rational traffic are preserved. No observed load violates a computed bound by more than the stated display unit.

## Four actionable route diagnoses

### B10: one demand creates the candidate's rank-five bottleneck

The first four equal ranks are already at bridge-cut floors within display precision. The candidate loses at rank five: **0.869291 vs 0.807464**. Its decisive physical coordinate is **slot 8, link 773 → 693**, not the bridge link responsible for the higher common ranks.

The exact candidate saturation on that link is **0.869291998929336188…**, and it is entirely contributed by **demand index 14926, source 230 → destination 693**. Candidate waypoints are `[231, 604, 605]`; SEDGE's saved route is `[231, 604, 191]`. That demand contributes zero to the same link under its SEDGE route. The total SEDGE load on the link, **0.160087380085653104…**, comes from other demands; it must not be attributed to demand 14926.

Copying this saved route at slot 8 alone fits the reconfiguration limits: used budget becomes 4 at boundaries 8 and 9, each with limit 10. Copying the demand's full saved horizon also fits. **These are budget checks only.** The route can move traffic onto other links, so neither substitution has been established as a full-vector improvement.

The ready proposal is `menus/setB-10-dock-route-menu.json`, bound to the original candidate incumbent.

### B02: a single contributing route, but a one-slot swap breaks budgets

Candidate loses at rank **47**, 0.092297 vs 0.089904. At **slot 4, link 69 → 103**, the entire exact load difference **+0.002392933333333333…** comes from **demand 1016, 69 → 42**: candidate has no intermediate waypoint; SEDGE uses `[34]`.

A single-slot copy consumes **12/10** at boundary 4 and **13/10** at boundary 5. It is not a legal isolated move. Copying the same demand's saved full-horizon schedule satisfies all transition budgets. This makes a complete temporal proposal more relevant than repeatedly trying a one-slot change. The full load-vector effect remains unevaluated.

Proposal: `menus/setB-02-dock-route-menu.json`.

### B07: two large opposing contributions hide a smaller net loss

Candidate loses at rank **2**, 0.554801 vs 0.543582. Its decisive link is **slot 7, 481 → 344**. At that same physical coordinate SEDGE has 0.517229, so the aligned gap is **+0.037572**, not the scalar rank gap.

Demand **1207, 481 → 405**, adds **+0.257701** relative to SEDGE: `[24,457]` versus `[427,102]`. Demand **2015, 481 → 110**, offsets **−0.220129**: `[140]` versus `[410]`. Undoing both indiscriminately would discard that helpful offset.

For demand 1207, the one-slot SEDGE route copy consumes **31/26** at boundary 7 and **32/26** at boundary 8. The full-horizon copy fits. The proposal file includes demand 1207 only, preserving the distinction between positive and negative hotspot contributions.

Proposal: `menus/setB-07-dock-route-menu.json`.

### B05: preserve the helpful route while testing two contributors

Candidate loses at rank **6**, 0.427543 vs 0.425636. On its decisive coordinate, **slot 9, 8 → 0**, exact candidate-minus-SEDGE load is **+0.009612630466390784…**. Three changed demand contributions explain it:

| Demand | Candidate → SEDGE waypoint | Candidate-minus-SEDGE contribution on this link |
|---|---|---:|
| 654 | `[461]` → `[242]` | +0.030693190918… |
| 93 | `[9]` → `[407]` | +0.026237091712… |
| 4256 | `[7]` → `[92]` | −0.047317652164… |

Both positive contributors' single-slot and whole-horizon copies satisfy the transition constraints. Demand 4256 currently helps on this coordinate; its route is deliberately excluded from the positive-driver menu. None of these budget-passing proposals has been scored on the complete objective.

Proposal: `menus/setB-05-dock-route-menu.json`.

## What the package establishes

The archive and all 288 payload hashes are checked. All 12 original outcomes and first differing ranks match; the complete 739,920 six-decimal saturation values are preserved in the underlying read. Twenty-four saved solutions' reconfiguration totals match both stats and checker costs. Exact rational contribution ledgers close on four selected physical hotspots, with eight existing 12-decimal observations agreeing within 1e-12.

The **32 passing tests** cover independent cut and path-enumeration oracles, direction and maintenance, exact scalar ranking, missing-budget defaults, route/menu integrity, and nonmutation. Two broken mathematical implementations produce the intended assertion failures. Full outputs, source, commands, hashes, and failure logs are included.

## Handoff state

The initial diagnosis and a subsequent direct-menu execution delta were posted in the canonical ROADEF thread; exact links and ownership boundaries are in `COORDINATION.md`. This directory publishes the reusable source/tests/results without editing the shared solver. The existing frozen continuation experiments remain unchanged, and S139's qualification draft/attachment stays unsent and untouched. The route menus are inputs for owned consumers, not a replacement for the current selected solver.

## Contest product (titanmcp)

Live judge pad (≠ Commons Shared Pad / ≠ Commons `/mcp`): https://webmcp-pad.vercel.app/ — **titanmcp 1.4.5**, 24 tools, Agent Resources, `syncConsents`. Board: [titanmcp.html](../../../titanmcp.html). Cite Latch Pad KEEP.
