# UIOWA-095 — measured preparation-workflow capacity

Baseline: `05e578767791b1ea66e74e0ff4698dbf1bbe9db1`

Synthetic import -> untrusted compile -> semantic verify -> canonical JSON export -> integrity-checking Markdown render. No live systems or University evidence.

| Sources | Input KiB | Report JSON KiB | Median ms | p95 ms | Peak Python KiB | Dominant stage |
|---:|---:|---:|---:|---:|---:|---|
| 12 | 7.7 | 16.1 | 3.148 | 3.566 | 153.0 | verify_ms |
| 96 | 58.3 | 89.8 | 19.847 | 23.855 | 866.6 | verify_ms |
| 240 | 144.9 | 216.1 | 47.830 | 49.510 | 2097.1 | verify_ms |

## Correctness

Every measured size retained 12 assessment cells, `UNTRUSTED_INSPECTION`, `current_evidence_review_authority=false`, a stable receipt, JSON round-trip receipt identity, and a Markdown render containing the verified receipt.

## Analyst steps

The current operator flow has **6** documented steps. This benchmark does not invent manual durations; it measures the automated preparation path only.

## Optimization decision

At the largest supported near-ceiling fixture (240 of 256 sources), the bounded pipeline remains comfortably below the 2 MiB HTTP intake ceiling and preserves all correctness invariants. The dominant stage is semantic verification/rendering, which intentionally recompiles before human-readable output. Skipping that safety boundary would trade evidence integrity for latency; no production compiler shortcut is justified by this benchmark.

This is a synthetic tooling benchmark, not a University capacity claim and not a fleet limit.
