# Committed-seed retry activation gate

Status: **NO PROMOTION EVIDENCE — keep `committed_seed_retry` default OFF.**

This gate used the pinned process-isolated official interpreter shipped with the current TITAN artifact. Both sides used the same executable-prefix correctness patch; the only A/B difference was `TITAN-CONFIG.json::committed_seed_retry` false vs true.

## Full-horizon observations

Panel seeds began at `1909087201` with paired seats and `episodeSteps=720`.
The local execution window ended before the requested panel finished, so these are observations only, not a completed gate:

- seed `1909087201`, feature-ON seat 0: `98,744` vs OFF `98,744` — tie
- seed `1909087201`, feature-ON seat 1: OFF `98,744` vs ON `98,744` — tie
- seed `1909087202`, feature-ON seat 0: `102,744` vs OFF `102,744` — tie

All three completed games had `status=complete` and no evaluator failure.

## Short-horizon attribution

Seed `1909087201`, `episodeSteps=144`, paired seats:

- ON seat 0: `559` vs OFF `559`
- ON seat 1: OFF `559` vs ON `559`
- summary: 2 scheduled / 2 completed / 0 failed / 2 ties / mean margin `0.0`
- both games produced the same whole-game trace SHA-256:
  `eab8bcabd2e109af835edb3c16572b9d67c716008c7b183ac20326ee056d6166`

The toggle therefore produced no observable early-game trace difference on this seed.

## Disposition

The correctness repair is composed and tested, but this evidence does **not** justify changing the default. Keep `Features.committed_seed_retry=False` until a completed current-head activation panel demonstrates a concrete positive delta or an explicitly targeted replay proves the feature reaches and improves a known loss cell.

Do not infer a negative economic effect from the incomplete full-horizon panel; the current conclusion is only **no promotion evidence**.
