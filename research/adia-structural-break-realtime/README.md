# ADIA Structural Break Real-Time — ZVK-R6M8 carrier

Operation: `ADIA-STRUCTURAL-BREAK-REALTIME-ZVKR6M8-20260914`  
Durable custody: Commons issue #14488  
Detector: `zvk-r6m8-v1`

This is a **public-source, synthetic-data-only** implementation carrier for the
2026 ADIA Lab / Crunch Structural Break Challenge: Real-Time Edition.

## Current public target

The current sponsor page advertises a **$100K USD** prize pool, May 6–October 1,
2026 duration, and teams of up to five. The live production Crunch competition
listing currently shows **100,000 $USDC** and `Ends 10/1/26`. Those two public
surfaces disagree on the prize *currency wording*, so `public_contract.json`
preserves both forms instead of pretending they are identical.

This is the **2026 sequential problem**, not the 2025 known-boundary problem:

- historical segment: 1,000–5,000 observations, delivered in full and guaranteed
  break-free by the public quickstarter;
- online segment: 10–1,000 observations, released one observation at a time;
- output: one score in `[0,1]` after each released online observation;
- metric: Time-Stratified AUC;
- cloud streams are single-pass.

The exact upstream commit/blob identities used to derive that contract are pinned
in `public_contract.json`.

## What this carrier improves over the public mean-only baseline

The organizer tutorial intentionally starts with a streaming EWMA mean-shift
baseline. `detector.py` stays streaming/O(1)-per-window but monitors five
families across 8/16/32/64-observation windows:

1. normalized level mean — location shifts;
2. normalized absolute level — variance/scale shifts;
3. first-difference mean — slope/trend shifts;
4. absolute first difference — volatility changes;
5. lag-one normalized product — dependence/persistence changes.

Historical normalization uses a median/MAD scale with a conservative standard
deviation floor. Online normalized residuals are clipped before feature updates.
Each family requires support from more than one timescale where possible, then a
decaying persistence accumulator converts evidence into a soft probability-like
score. This design was chosen after hostile review exposed false-alarm and
historical-scale sensitivity paths; the repaired detector requires corroboration
across windows and uses a robust historical scale floor.

## Strict causality and bounded state

`OnlineBreakDetector.update(point)` sees only:

- immutable summaries derived from the historical reference segment;
- the current point;
- bounded state from the already-released online prefix.

It does **not** receive online length, future observations, a rewindable stream,
or another series' state. Five rolling families over four windows retain at most
`5 * (8+16+32+64) = 600` online scalar cells per active series.

## Crunch seam

`submission.py` follows the current public tutorial contract:

- `train(datasets, model_directory_path)` writes a transparent JSON artifact;
- `infer(datasets, model_directory_path)` loads that artifact;
- first `yield` is the readiness handshake;
- then exactly one float is yielded for every current online point;
- `INFER_PARALLELISM = 4`; inference has no mutable global model state.

V1 intentionally has **no pretrained weights and no hidden learned parameters**.
A later supervised calibration stage can be added only with source-visible
training and participant-side competition data custody.

## Synthetic engineering proof

Run:

```bash
python -m unittest discover -s tests -p 'test_*.py' -v
python -m py_compile detector.py submission.py synthetic.py tests/test_detector.py
python -c "import json; from synthetic import benchmark; print(json.dumps(benchmark(32), indent=2, sort_keys=True))"
```

### Historical pre-hardening receipt

The original authored carrier recorded **17/17 PASS** plus a 32-seed synthetic
receipt with trend median delay **41.5** and persistence median delay **38.0**.
Those values describe that earlier source generation only. Detector hardening in
`bd6b45abe92c563360cd02a2cd138dd55ff9f413` changed corroboration / robust-scale
semantics, so reusing the old exact delay receipt for the repaired detector would
be stale evidence.

### Current repaired exact-head hosted proof

GitHub Actions dedicated run `34933981146`, job `104267862275`, on the repaired
receipt donor merge ref completed successfully under Python **3.11.16**:

- `py_compile`: **PASS**;
- detector + robustness tests: **20/20 PASS**;
- exact `synthetic_benchmark_receipt.json` replay: **PASS**;
- 32-seed synthetic smoke at alarm threshold `0.5`:
  - null false-alarm rate: **0/32**;
  - null max-score median: **0.012953727530695859**;
  - mean-shift hit rate: **32/32**, median delay **8.0** points;
  - variance-shift hit rate: **32/32**, median delay **10.5**;
  - trend-shift hit rate: **32/32**, median delay **42.5**;
  - persistence-shift hit rate: **32/32**, median delay **42.0**.

These are deliberately labeled **synthetic engineering regressions**. They are
not organizer TS-AUC, not a challenge score, and not a leaderboard/rank/prize or
payout claim.

## Hostiles covered

`tests/test_detector.py` and `tests/test_detector_robustness.py` check:

- mean and variance change detection;
- dependence change with approximately preserved marginal variance;
- one-outlier false-alarm resistance;
- exact warmup-impulse rejection;
- long-horizon single-impulse alias rejection;
- historical-tail outlier resistance without erasing a later true mean break;
- null false-alarm resistance;
- prefix invariance under an adversarial future suffix;
- byte-deterministic repeat replay;
- cross-series state isolation;
- true one-pass online iterable behavior;
- no future-horizon dependency;
- fixed state bound through 600 online points;
- NaN/Inf historical and online fail-closed behavior;
- too-short historical fail-closed behavior;
- model-artifact tamper rejection;
- score range under huge finite adversarial magnitudes;
- multi-seed synthetic benchmark regression.

## Hard authority/data fence

This source carrier performs **no** Crunch account creation/login, terms
acceptance, competition-data download, token use, provider submission,
leaderboard mutation, USDC wallet/payout mutation, paid compute, score/rank,
prize, payment, or revenue claim.

Participant-side entry and organizer data remain separate future actions. Never
copy restricted competition bytes into this repository or hosted model APIs unless
the operative competition terms explicitly authorize that publication/transfer.
