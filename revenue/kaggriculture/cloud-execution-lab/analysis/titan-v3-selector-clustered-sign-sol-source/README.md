# TITAN V3 clustered sign selector

This packet repairs a statistical custody error in sparse mirrored panels. A mirrored player-position pair is a matched replication of one opponent/seed condition, not automatically two independent Bernoulli sign trials. Counting every positive position row independently can turn deterministic mirror duplication into false exact significance.

## Predecessor witness

Retained artifact `10168056904` (ZIP SHA-256 `528f7557a899c1376c8fe04ed328c70a17a760aa3a725e190710ea13ad7e13f8`, exact head `c3c2668d4822713afb126579f2f253788372f6ea`) has 32 paired cells and six positive own-cash rows. Those six rows collapse to:

- three nonzero `(opponent, seed)` blocks, all positive: exact one-sided tail `1/8 = 12.5%`;
- two nonzero seed clusters, both positive: exact one-sided tail `1/4 = 25%`.

The naive six-row value `1/64` assumes independence that the design does not establish. Every changed seat pair is terminal-delta identical. Seed `2609097301` supplies `216/268 = 80.6%` of total positive own cash. Six of eight seed-cluster effects are exactly zero, so the ordinary nonparametric seed bootstrap has exact all-zero resample mass `(6/8)^8 = 6561/65536 ≈ 10.01%`; therefore its 2.5th percentile is exactly zero.

The factor remains a useful, zero-negative-cell port hypothesis. The corrected disposition is `MORE_EVIDENCE`, not regression and not an exact 5%-level advance.

## Gate

`clustered_sign_gate.py`:

- validates unique `(opponent, seed, seat)` cells and complete mirrored-seat blocks;
- rejects nonfinite/boolean score data, inconsistent margins, and score deltas without candidate-action activation;
- reports the naive cell sign tail as diagnostics only;
- computes exact rational tails at `(opponent, seed)` and seed levels;
- retains concentration, exact all-zero seed-bootstrap mass, and leave-one-seed-out results;
- routes sparse clean panels that miss the declared clustered threshold to `MORE_EVIDENCE`.

The conservative default experimental unit is the environment seed. Clearing both declared clustered tails with no negative own-cash cell yields `SIGN_SUPPORTED`, not a promotion verdict. This receipt must still be composed with tested-action causality, own-cash and margin safety, W/T/L nonregression, exact-current-base closure, and package custody. Its exact binomial arithmetic is conditional on the experiment justifying exchangeable independent seed clusters; the tool does not manufacture that sampling assumption.

## Run

```bash
python -m unittest -v test_clustered_sign_gate.py
python clustered_sign_gate.py ABLATION-REPORT.json \
  --artifact-id 10168056904 \
  --artifact-sha256 528f7557a899c1376c8fe04ed328c70a17a760aa3a725e190710ea13ad7e13f8 \
  --git-head c3c2668d4822713afb126579f2f253788372f6ea \
  --output PR11963-CLUSTER-REANALYSIS.json
```

Evidence only. This packet changes no agent, feature, route, canonical archive, release pointer, provider, Kaggle state, or submission.
