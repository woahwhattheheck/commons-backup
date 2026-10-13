# UIOWA-095 — production-workflow capacity benchmark

This carrier measures the existing RFQ 18649 evidence/report preparation path rather than inventing a parallel benchmark implementation. It uses synthetic evidence only and imports the existing `../uiowa_rfq_18649_workshare` compiler.

## What is measured

For **12**, **96**, and **240** synthetic evidence records, the harness runs:

1. strict JSON import;
2. `UNTRUSTED_INSPECTION` compilation;
3. semantic integrity verification;
4. canonical JSON export; and
5. integrity-checking Markdown render.

The 240-record case is deliberately close to the current 256-source contract ceiling. Timing samples use `time.perf_counter_ns`; peak Python allocations are measured separately with `tracemalloc` so memory tracing does not contaminate latency samples. The checked-in measurements use 25 timed iterations after a warmup.

The human operator flow is recorded as **six documented steps** from the current workbench README. No analyst-duration estimate is invented.

## Reproduce

From this directory in the Commons checkout:

```bash
python3 selftest.py
python3 -O selftest.py
python3 benchmark.py --iterations 25 --json-out MEASUREMENTS.json --md-out MEASUREMENTS.md
```

`benchmark.py` refuses to run if any of the ten compiler modules that define normalization, assessment, compile, semantic verification, or render behavior no longer matches the Git blob recorded for baseline commit `05e578767791b1ea66e74e0ff4698dbf1bbe9db1`. That makes the historical measurement reproducible instead of silently benchmarking changed semantics.

## Recorded environment and results

The checked-in run records its environment in `MEASUREMENTS.json`: CPython 3.13.5, Linux x86_64, five visible CPUs. Those figures describe the measurement environment; they are **not** a production SLA, fleet limit, or University capacity claim.

At 240 sources, the recorded input is about **144.9 KiB** (about **7.1%** of the workbench's 2 MiB HTTP request ceiling). The measured automated pipeline median is about **48.7 ms**; peak traced Python allocations are about **2.05 MiB**. These are different metrics: the memory peak is not an HTTP payload limit.

Semantic verification and the integrity-checking Markdown renderer are the dominant stages because each recompiles/validates evidence semantics. The measured workflow preserves all authority/receipt invariants, so this carrier does **not** remove or bypass those checks merely to reduce latency. No production compiler change is justified by these measurements; the implemented improvement is the reproducible capacity/provenance harness itself.

## Correctness boundary

Every measured size must retain:

- exactly 12 ESS/RIS/IAM × software/security/deployment/AI-readiness cells;
- `mode == UNTRUSTED_INSPECTION`;
- `current_evidence_review_authority == false`;
- stable deterministic receipts;
- receipt-preserving JSON round trips; and
- Markdown output containing the semantically verified receipt.

All fixtures explicitly state that they are synthetic and are not University findings. The harness performs no live-system access, customer contact, scheduling, purchasing, submission, or commercial authorization.
