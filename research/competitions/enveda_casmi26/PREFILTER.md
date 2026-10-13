# CASMI26 R2 mass prefilter

Measured performance follow-on to the R1 ranker.

## Purpose

The expensive part of a full CASMI26 notebook should only see rows that are
mass-plausible for at least one test molecule. `casmi26_mass_prefilter.py`
works on a whole precursor/adduct batch with NumPy, computes neutral masses, and
uses sorted-query `searchsorted` checks to return a boolean retention mask.

Only the retained rows should be materialized into Python objects for the R1
fragment/neutral-loss scorer. This is designed for Arrow/Parquet record-batch
integration without requiring PyArrow inside the reusable core.

## Focused receipt

Command:

```bash
python casmi26_mass_prefilter.py --selftest --benchmark --rows 2500000 --queries 400
```

Observed on the authoring cloud harness:

- selftest: PASS
- rows: 2,500,000
- query masses: 400
- ppm: 15
- retained rows: 42,055
- retained fraction: 1.6822%
- injected near-hits: 1,600
- injected retained: 1,600 / 1,600
- elapsed: 0.503 s
- throughput: ~4.97M input rows/s

The selftest includes randomized vectorized-vs-scalar equivalence across 5,000
masses. This remains a synthetic throughput/correctness receipt, not a CASMI
chemistry or leaderboard result.

Source SHA-256:
`f7bdff2aa56d4f61d763d61b941d829cf85f878212817c69d21290d8aff5d340`
