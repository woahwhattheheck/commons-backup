# F3 / NIGHT-FEED / opening-book current-native reachability

**Disposition: `BLOCKED_AT_NATIVE_ASSEMBLY`.**

The recovered F3 V217 engagement materializer, NIGHT-FEED proposal, and opening-book rebound all exist as source/evidence, but the canonical production package does not currently call any of those seams. The live path remains `main.py -> TitanAgent -> FrozenSelected`; the current runtime has no callable `_v217_plan`, `propose_feed_tails`, or `OpeningBookRebound` lifecycle binding, and `TITAN-CONFIG.json` carries no target key.

The ALDER `SeedBudget` already used by production is deliberately not treated as opening-book integration. Opening-book requires its own module binding, `OpeningBookRebound` construction, and lifecycle call before it can be considered reachable.

`NIGHT-FEED-HANDOFF.md` is consistent with this result: its measured fixed-tape witness is proposal evidence, while composed current runtime execution was explicitly not claimed. The current acceptance boundary is actual returned-unit binding before snapshot/history commit.

## Two-layer evidence

The live source pins are recorded in `CURRENT-NATIVE-REACHABILITY.json`. An authenticated native artifact (`10175943272`, `final-pressure-runtime`) independently returns the same `BLOCKED_AT_NATIVE_ASSEMBLY` result under the checker. That artifact is historical, not mislabeled as current: its `titan_runtime.py` is the older blob `b952c9c2...`, while live source is `6d9720f4...`. `main.py`, `frozen_selected.py`, `scheduler.py`, and `TITAN-CONFIG.json` match between that artifact and the live audit.

## Why there is no economics number

Running ON/OFF economics by source-transforming donor `r04_full_router.py`, or by invoking the opening/NIGHT-FEED helpers from a harness that production never calls, would answer a synthetic question. This gate therefore stops before economics. Once canonical production has a real callable seam, this same checker changes to `BOUND_REQUIRES_RUNTIME_GATE`; only then should the existing both-seat current-native execution machinery measure natural engagement, fallback/deadline custody, state parity, and terminal economics.

## Fail-closed contract

`check_current_native_reachability.py` scans only production-root Python modules, not candidate/research text. Comments, strings, import-only references, candidate self-reference, generic `SeedBudget`, and config-only hints do not prove reachability. Missing core files, malformed Python, or an unrecognized native call chain fail closed. The focused suite covers those mutation classes in normal and optimized Python.

No controller, router, config key, default, archive, Kaggle package, or production runtime is added or changed by this packet.
