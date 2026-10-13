# EEG/EMG Foundation Challenge 2026 — Sleep-onset Ridge alpha sweep

Public-safe benchmark for Track 03 (sleep onset). It reproduces the official repository's zero-download **Simulated** proxy and warm-up binned-MAE definition, then measures the regularization constant used by the shipped Mean-Ridge baseline.

## Result

Command:

```bash
python sleep_onset_alpha_sweep.py
```

50 independent seeds (`0..49`), each with the official simulated shape (300 train / 150 test, 4 channels, 500 samples):

| Ridge alpha | mean bMAE (s) | median bMAE (s) | p95 bMAE (s) | mean MAE (s) |
| ---: | ---: | ---: | ---: | ---: |
| 1.0 | 3.655773 | 3.290401 | 6.219659 | 3.641919 |
| 0.1 | 3.220386 | 2.842303 | 5.686816 | 3.195398 |
| 0.01 | **3.188184** | **2.819270** | **5.673213** | **3.161400** |

Relative to the official Mean-Ridge default `alpha=1`, `alpha=0.01` lowers mean simulated bMAE by **12.790%** and wins on 49/50 seeds. On the competition training-config seed 42, bMAE moves from **3.176147** to **3.064817**.

## Evidence boundary

This is **not** a Sleep-EDF result and **not** sealed Muse evidence. The public competition repo states:

- warm-up scoring here is unweighted bMAE over `[0, 40, 90, 300, 600]` seconds plus plain MAE;
- the final Muse phase uses W-bMAE with seen/unseen-subject macro-averaging;
- the sealed scorer ships with the final Muse evaluation data.

The result is therefore a low-cost hypothesis: the default Ridge regularization is over-strong even on the official smoke proxy. The next performance lane should test a validation-selected alpha on the public Sleep-EDF pipeline before changing a competition artifact.

## Source pins

Measured against the public `neural-interfaces26/2026-competition` Track 03 implementation on 2026-10-05:

- `tracks/sleep_onset/objective.py`
- `tracks/sleep_onset/datasets/simulated.py`
- `tracks/sleep_onset/solvers/mean_ridge.py`

No account, registration, rules acceptance, Codabench submission, or private challenge data is required for this benchmark.
