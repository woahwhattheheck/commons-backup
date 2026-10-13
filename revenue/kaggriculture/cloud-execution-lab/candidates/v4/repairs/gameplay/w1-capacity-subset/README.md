# W1: capacity-subset recovery with executable market-prefix admission

This is the existing W1 repair package in the single `main/candidates/v4` workspace. It is not another agent, feature key, integration branch, or production activation. The donor helper and its original regression remain untouched under `donor/overlay`.

## Current source

Consume `r04_dead_water_harvest.py` blob `2be707cac86940728e75100447a354a10e2422a2`. It composes the original subset improvement (`f56a453234edaf3e214d61247f761a7cd2e92bb9`) with the narrow ASTRA-W1-RAW-PREFIX continuation in this same file. `MANIFEST.json` identifies the current postimage and keeps the complete earlier subset-stage execution record explicitly historical.

The subset algorithm maximizes **whole harvested units**, not cash or expected game margin. Yields `[6, 4]` with four free units select the second harvest; `[6, 5, 5]` with ten free units select both five-unit harvests. Equal totals choose the lexicographically earliest actor-index tuple. At most 101 capacity states are retained; yield magnitude and the worker powerset do not determine allocation size.

All existing crop, maturity, future-yield, geometry, day, private-inventory, and final capacity predicates remain unchanged. The only eligible callback is still step 695. Existing cargo and authored HARVEST/COLLECT_FERTILIZER inflows are reserved first. All-fit behavior bypasses the selector; every partial set must pass the unchanged `_capacity_safe`. No sale, future consumption, or capped suffix is credited as storage room. Unselected actors retain WATER; no-fit and disabled paths retain exact action identity.

## Raw-prefix correction

The exact official engine first forms `market[:max(1, maxMarketOrdersPerTurn)]`, then parses orders. The predecessor incorrectly consulted every authored row, so an engine-inert suffix BUY_PRODUCT, BUY_ANIMAL, or malformed row could veto an otherwise certified recovery.

The current admission checks only that executable **raw** prefix. It never filters placeholders before truncation and never edits, compacts, reorders, or copies the returned market vector. Original active-prefix malformed-row and shed-inflow vetoes remain intact. An absent cap retains the engine default of 10; an explicit cap must be a plain integer. Zero and negative integers clamp to one. Dictionary and attribute-shaped configuration are supported; explicit malformed caps and configuration-read exceptions fail closed.

Concrete constructed-state witness: shed WHEAT98, two eligible TOMATO yields `[2,2]`, cap1, and market `[BUY_SEED WHEAT1, BUY_PRODUCT WHEAT100]`. The predecessor recovers nothing; the current helper delivers two TOMATO units at EOD. The capped buy never executes. If the buy becomes executable, admission correctly vetoes; forcing HARVEST with one actual WHEAT buy discards one TOMATO at EOD. This is a delivery/capacity witness, not an economic or win-rate claim.

## Executed current-source evidence

Cloud-session CPython 3.13.5: **40/40 normal and 40/40 optimized**. The exact existing 25-test subset suite remains unchanged and passes, including 17,745 exhaustive subset-oracle comparisons and 832 action/capacity/nonmutation cases. The new 15-test suite adds 112 cap/suffix contracts and 448 constructed both-seat worlds. Each world executes full official-interpreter baseline, candidate, and suffix-truncated candidate arms; extra controls bring the count to 1,350 interpreter calls per mode. Candidate and truncated arms match completely. Baseline/candidate private-state differences equal the selected harvest delivery, with unchanged cash, market, town, and rival state.

Exact predecessor `f56a4532` produces 565 failing subcases in each mode. Six deliberately broken variants are rejected in both modes: uncapped scan, off-by-one cap, lost configuration, filter-before-cap, missing minimum-one clamp, and cap coercion. Four missing/drifted engine/specification input gates fail in each mode rather than skipping. Source and test Git blobs returned by GitHub match the executed local bytes. `py_compile` passes. Sixteen predecessor functions are source-identical; only market admission and its entrypoint call change.

`RAW_PREFIX_VERIFICATION.json` contains hashes, per-suite results, controls, and scope. The full engine is pinned to `3c202c7ee921da239356789e266b694635103fc4`, with adjacent JSON `b354d06b742fe48402513792253f1a5c29366b20`. Its seed-resolver import adapter raises if called; the initializer is not used. These are constructed-state interpreter checks, **not full games, current-router wiring, hosted package validation, or economic promotion**. The legacy 27-test donor suite was not rerun for this continuation; its earlier 52-test combined receipt is preserved as historical evidence bound to `f56a4532`, not relabeled as a current run.

## Reproduce from repository root

Provide the exact official engine and adjacent `kaggriculture.json`. This session recovered both from existing artifact `10285621024`, members under `seed-retry-runtime/checks/reference/engine/`; no workflow was dispatched.

```sh
V4=revenue/kaggriculture/cloud-execution-lab/candidates/v4
REPAIR="$V4/repairs/gameplay/w1-capacity-subset"
export TITAN_W1_ENGINE=/absolute/path/to/kaggriculture.py
PYTHONPATH="$REPAIR" python "$REPAIR/test_v4_w1_capacity_subset.py" -q
PYTHONPATH="$REPAIR" python "$REPAIR/test_v4_w1_raw_prefix.py" -q
PYTHONPATH="$REPAIR" python -O "$REPAIR/test_v4_w1_capacity_subset.py" -q
PYTHONPATH="$REPAIR" python -O "$REPAIR/test_v4_w1_raw_prefix.py" -q
```

## Single-V4 consumption

Consume this same-package successor once, preserving any later independent W1 work. Do not reapply the old whole-file `f56a4532` over it. Re-run current composition/package and competitive gates before any activation. Feature defaults remain unchanged. Do not execute the legacy r04 materializer against the incompatible current production runtime. No donor, runtime, archive, workflow, evaluator, opponent, or Kaggle state change accompanies this continuation.
