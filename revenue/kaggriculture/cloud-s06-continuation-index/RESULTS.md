# S06 compressed continuation index source checkpoint — 2026-09-09

Operation: `titan-v25-orders-20260909-S06`

## Scope

This checkpoint adds a standalone, run-only continuation index for later official-engine experiments. It does **not** modify the canonical TITAN runtime or default action path.

The implementation provides the three requested retrieval variants over the S06 public feature projection (`phase`, `positions`, `resources`, `structures`, `animals`, `market`, `commitments`):

- exact SHA-256 feature hash;
- product-quantized feature hash;
- retrieve-at-most-32 historical continuations followed by an optional caller-supplied current economic score.

Every retrieval unions caller-supplied canonical actions. Historical candidates are deduplicated against canonical actions and fail closed on explicit funding, seed, route, or caller legality conflicts. The module returns a candidate union/order only; it never selects or promotes a final action. Unknown labels such as future outcomes are excluded from the index projection.

The corrected index has deterministic structural admission accounting with a hard default budget of 128 MiB. It charges the empty owned graph up front, then charges each decoded retained record at twice its recursive `sys.getsizeof` footprint plus a 1 KiB reserve. The benchmark separately records the retained object graph and Python `tracemalloc` usage; neither is mislabeled as RSS.

## Correctness checks

Corrected source-author checks after independent review:

```text
python -m unittest -v test_continuation_index.py
Ran 19 tests in 0.020s
OK

AST_OK continuation_index.py
AST_OK test_continuation_index.py
AST_OK benchmark_continuation_index.py
```

The original 15 contracts remain covered. Four additional review regressions now prove:

1. Explicit falsy malformed top-level `requires` values (`[]`, `''`, `0`, `False`, `None`) fail closed as `malformed_requirements`.
2. A malformed historical continuation is rejected while the caller-supplied canonical action remains in the union.
3. A budget set one byte below the exact prospective record admission charge raises before any index-owned container changes.
4. Across a 256-record adversarial sample, the monotonic admission charge is at least the recursively measured retained Python object graph and never exceeds the configured budget.

## Post-review memory evidence

The reviewer correctly found that the original payload-oriented charge understated this checkpoint's own 20,000-record traced footprint (16.24 MB charged versus 22.74 MB traced peak). The corrected charge is tied to the actual decoded Python record graph instead of compact JSON length.

For the same deterministic 20,000-record workload, three corrected runs produced identical memory accounting:

```text
records 20000
admission_bytes 75445248
structural_bytes 23545032
tracemalloc_current_bytes 23857912
tracemalloc_peak_bytes 24000091
wall lookup p50: 1.717-1.745 ms
wall lookup p95: 2.156-2.175 ms
wall lookup max: 47.319-63.309 ms
```

Thus the 75.45 MB admission charge is above both the 23.55 MB recursive retained object graph and the 24.00 MB traced peak for this panel. A separate default-budget boundary probe admitted 35,581 representative records, then rejected the next record with `admission_bytes=134216780`, `max_bytes=134217728`, and only 948 charged bytes remaining; traced peak at that boundary was 40,820,249 bytes.

The cloud VM showed rare wall-clock scheduling outliers above 20 ms even though p95 remained about 2.2 ms. Therefore this correction **does not claim a hard 20 ms worst-case lookup result** from the local VM. The official-engine S/H panel must still establish the requested runtime/action/outcome evidence under the canonical harness.

## Required remaining S06 evidence

No official-engine full games were run in this VM because shell Git repository materialization is DNS-blocked. Therefore this checkpoint makes **no held-out action, terminal outcome, win-rate, or promotion claim**.

Before any canonical integration, a game-capable peer must source-pin the current canonical archive and run the requested S-versus-no-index panel plus held-out H screen, verify zero legality mismatches, compare exact vs quantized vs retrieve-32/economic-rerank, and report held-out action/outcome improvement. Compression alone is not a promotion criterion.

## Contest product (titanmcp)

Live judge pad (≠ Commons Shared Pad / ≠ Commons `/mcp`): https://webmcp-pad.vercel.app/ — **titanmcp 1.4.5**, 24 tools, Agent Resources, `syncConsents`. Board: [titanmcp.html](../../../titanmcp.html). Cite Latch Pad KEEP.
