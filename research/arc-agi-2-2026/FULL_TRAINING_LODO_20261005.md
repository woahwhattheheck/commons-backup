# ARC-AGI-2 complete public-training LODO baseline — 2026-10-05

This receipt measures the existing deterministic solver without changing its
model or hypothesis library. Each public training demonstration is held out in
turn, the remaining demonstrations are supplied to the solver, and the held-out
output passes when either `attempt_1` or `attempt_2` is an exact match.

## Source fence

- Commons source commit: `9203282aa14743e3fa2a2ee973e2550060e264dd`
- Solver: `arc2_baseline.py`
- Solver SHA-256: `192dbf779273a414c6c0249f50d951bb539e139df2e5a000784b0b8a31822d8c`
- Official data repository: `arcprize/ARC-AGI-2`
- Official data commit: `f3283f727488ad98fe575ea6a5ac981e4a188e49`
- Training-corpus digest: `f2e5ad8fd1f0501ac8cfd2b143f80b8fb1f30dc40ba04a765f1d2c389eb30385`
- Corpus coverage: all 1,000 public training task files; zero skipped tasks

The corpus digest is computed over each lexicographically ordered relative path
and its exact bytes, with explicit path and payload lengths.

## Result

| Measure | Result |
| --- | ---: |
| Held-out demonstration folds | 3,232 |
| Exact pass@2 folds | 134 |
| Fold pass@2 rate | 4.1460% |
| Tasks passing every held-out fold | 33 / 1,000 |
| All-fold task rate | 3.3000% |
| Primary wall time | 13.804 s |
| Primary peak RSS | 14,720 KiB |
| Repeat wall time | 13.446 s |
| Repeat peak RSS | 14,720 KiB |

The second complete execution produced identical per-task outcomes and identical
logical counts. Runtime and memory are measurements of this cloud Linux / Python
3.12.14 environment, not Kaggle runtime predictions.

## Reproduction

```bash
python3 research/arc-agi-2-2026/benchmark_lodo.py \
  /path/to/ARC-AGI-2/data/training \
  --solver-source-commit 9203282aa14743e3fa2a2ee973e2550060e264dd \
  --dataset-source-commit f3283f727488ad98fe575ea6a5ac981e4a188e49 \
  --output research/arc-agi-2-2026/full-training-lodo-20261005.json
```

The raw JSON retains all 1,000 task IDs and their fold/pass counts. Its SHA-256
before publication was `b3bffc667e6a1ac221bca0717d8e08035c56883ec8598ab90a3de55c65f4bb8e`.
The benchmark runner SHA-256 was
`41959d7e2ee49e71e0e1c926bfdca6450f596e9a663b34c9256ae98d7961a4c4`.

## Interpretation boundary

This is a source-bound cross-validation diagnostic, not a Kaggle submission,
leaderboard score, public-evaluation score, prize claim, or estimate of private
test performance. Leave-one-demonstration-out is also stricter and structurally
different from normal competition inference, where every demonstration is
available. No public evaluation task was inspected or used for tuning.

Competition money state at measurement: $700,000 total advertised; funding not
independently verified; $0 awarded, invoiced, or received by this entrant.

