# Static vs bitemporal benchmark

This benchmark is the first falsification gate for the temporal evidence core in the parent directory. It is deliberately **synthetic, deterministic, and non-PHI**. It is not the NIH shared benchmark, does not establish biomedical or clinical superiority, and makes no eligibility, submission, award, payment, or revenue claim.

## Systems under test

**STATIC** is intentionally ordinary: it collapses all corrections to a latest-known final graph, ignores valid-time and knowledge-time query cutoffs, uses the latest surviving value for snapshot questions, and runs ordinary directed BFS for path questions.

**TEMPORAL** uses `TemporalEvidenceGraph`: assertions have both validity intervals and observation times; retractions/supersessions are append-only evidence events; snapshots honor both clocks; paths require non-decreasing hop times and each edge must be valid and known at the relevant cutoff.

The benchmark includes neutral controls that STATIC is expected to solve. A temporal win is therefore not built into every case.

## Corpus

`cases.json` contains 14 deterministic cases across four temporal failure classes plus controls:

- **control** — five neutral cases where both systems should be correct;
- **future_leakage** — evidence observed later must not leak into an earlier knowledge state;
- **impossible_path** — a static chain exists, but no time-respecting ordering can traverse it;
- **stale_retracted_fact** — later correction must not rewrite what was knowable at an earlier cutoff;
- **validity_window** — a fact or edge outside its validity interval must not answer the query.

All records are synthetic examples using placeholder entities such as recommendations, safety signals, version labels, and graph nodes. They contain no patient data or protected health information.

## Predeclared metrics

The runner reports, separately for STATIC and TEMPORAL:

- total correct / errors / exact-answer accuracy;
- per-error-class totals, correct answers, and errors;
- control accuracy;
- abstention / no-path correctness;
- runtime in nanoseconds.

Runtime is reported but deliberately excluded from the semantic receipt hash because it is host-dependent.

## Promotion / falsifier rule

The temporal thesis passes this synthetic gate only when:

1. TEMPORAL produces fewer errors than STATIC across the temporal-adversarial classes; and
2. TEMPORAL does **not** reduce control accuracy.

If the static baseline ties correctness with materially lower complexity/runtime, or if the temporal system regresses neutral controls, treat the thesis as falsified or in need of redesign. Do not polish a competition narrative around a failed gate.

## Run

From `research/nih_temporal_kg_2026`:

```bash
python -m unittest -v test_temporal_evidence.py benchmark/test_benchmark.py
python -O -m unittest -v test_temporal_evidence.py benchmark/test_benchmark.py
python benchmark/run_benchmark.py --output benchmark-result.json
```

Run only the benchmark suite:

```bash
python -m unittest -v benchmark/test_benchmark.py
python -O -m unittest -v benchmark/test_benchmark.py
```

## Current synthetic result

On the authored 14-case corpus used to validate this package:

- STATIC: **5 / 14 correct**;
- TEMPORAL: **14 / 14 correct**;
- STATIC temporal-adversarial errors: **9**;
- TEMPORAL temporal-adversarial errors: **0**;
- control regression: **false**;
- promotion gate: **pass**.

STATIC's nine adversarial errors break down as four future-leakage errors, one impossible-path error, two stale/retracted-fact errors, and two validity-window errors.

These numbers are **only synthetic engineering evidence**. They do not establish performance on NIH data, biomedical knowledge graphs, real clinical tasks, or any external benchmark.

## Integrity and reproducibility

`run_benchmark.py` validates the dataset schema before execution. Expected answers live in the corpus; they are never inferred from either system under test. Results bind:

- canonical dataset SHA-256;
- SHA-256 of the benchmark implementation;
- SHA-256 of the temporal engine implementation;
- every per-case expected/static/temporal outcome;
- aggregate metrics and promotion decision.

The deterministic `receipt_sha256` excludes runtime measurements. Changing a semantic input, expected answer, implementation digest, per-case outcome, metric, or promotion decision changes the receipt. `verify_result()` rejects malformed or rehashed semantic tampering covered by the result contract.

## What should happen next

This corpus proves the harness can expose the temporal failure modes it was designed to measure. The next evidence step is not more synthetic cases for their own sake: bind a public, non-PHI biomedical/evidence-evolution corpus; predeclare mappings and expected answers; add a static-KG reference implementation; then measure correctness, leakage, stale-evidence errors, runtime, and ablations under the same receipt contract.
