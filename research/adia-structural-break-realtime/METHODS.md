# Methods and competitive next steps

## Detection model

The detector converts the historical reference into a robust fixed profile and
scores the live prefix with five complementary statistics. For each feature
family, standardized departure is computed over rolling windows of 8, 16, 32,
and 64 observations. The second-largest available timescale statistic is used
when two or more timescales are ready. This is a deliberate robustness choice:
a genuine persistent break propagates across windows, while a one-sample impulse
is concentrated in the shortest window.

The maximum supported family evidence feeds:

`state_t = max(0, 0.85 * state_(t-1) + clip(evidence_t - 3.5, -0.6, 1.5))`

and the score is a logistic mapping of that state. The clipping/decay constants
are frozen in v1 and covered by synthetic regression tests.

## Why these channels

- **Level mean** catches mean/location changes.
- **Absolute level** catches scale/variance changes without letting a single
  squared residual dominate.
- **Difference mean** exposes persistent slope changes.
- **Absolute difference** exposes volatility changes.
- **Lag product** exposes correlation/persistence changes that can preserve the
  one-point marginal distribution.

The organizer metric compares scores across series at the same online time step,
so a pure function of time earns no useful ranking signal. Every v1 score depends
on that series' historical profile and revealed observations.

## Known limitations

1. The score mapping is heuristic, not yet supervised-calibrated against the
   organizer training distribution.
2. Heavy-tailed or nonstationary historical references may need richer robust
   reference features.
3. Abrupt distribution-shape changes that preserve the monitored moments can be
   missed.
4. The second-timescale support rule trades some earliest possible detection for
   false-alarm resistance.
5. No participant-side TS-AUC has been measured in this carrier.

## Highest-value participant-side successor

Once the owner has entered the competition and can legally keep competition data
inside an approved local environment:

1. run the exact v1 adapter through `crunch test` against the organizer data;
2. save raw per-time-step predictions and compute TS-AUC by fold;
3. fit a small source-visible calibrator on causal features only;
4. add distribution-shape channels (quantile sketches / robust signed-rank
   evidence) if ablations prove value;
5. evaluate per-DGP and per-break-time slices to distinguish fast detection from
   false alarms;
6. preserve deterministic inference and strict one-pass semantics;
7. submit only after local determinism and exact bundle verification.

Do not tune against public leaderboard noise without retained local validation.
