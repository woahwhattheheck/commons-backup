# ASTRA-LIMINAL — seven-lane rescue

This is one research package on the **single canonical TITAN V4 line**.  It closes the
seven `NEEDS-LOOK` labels from Riot's dead-lane audit without creating seven sibling
controllers and without pretending that missing historical workspace files were
recovered.

## What survived

Three historical all-ins are not worth resurrecting:

* `mono-carrot`: about **-$10.7k** in the historical degenerate leaderboard.
* `seed-hoard`: about **-$11k** overall.
* `mono-melon`: about **-$16k**.

The useful exception is inside the losing `seed-hoard` experiment: its receipt
reported two seeds where **not starting the crop program** improved outcome by
roughly **$6k-$27k**.  That does not justify hoarding seeds.  It motivates a much
narrower, current-compatible question: can TITAN reject an *optional new crop
commitment* when a verified conservative value floor proves the incremental
commitment negative?

`planting_regime_gate.py` is the executable research kernel for that question.

## Gate contract

The kernel deliberately fails open:

* existing crop commitments are always admitted;
* required obligations are always admitted;
* missing, unverified, negative, NaN, or infinite economic inputs are admitted;
* there is no crop-wide ban and no memory of a crop category;
* only a new optional commitment with an explicitly `verified_floor=True` and a
  strictly negative lower-bound incremental margin is rejected.

The kernel is **not wired into `main.py`**.  A current-native adapter needs a real
pre-commit planting boundary plus both-seat paired economics before any production
promotion.  This keeps SeedBudget, crop-release, WATER/CARE, harvest, final-action
commit, and receipt owners authoritative.

## The other ambiguous labels

`production-side care-bank`, `tomato_program`, and `B4` remain quarantined evidence:
their exact source/base/config receipts were not recovered on current `main`.
Bench CARE work is not silently substituted for production `care-bank`, and the
historical `MONO-TOMATO` loss is not silently relabeled as `tomato_program`.

`water-only PASS` resolves to a guardrail, not a policy.  The recovered due-day
water receipt explicitly rejects “today's-water-only-for-tomorrow” cases; watering
is load-bearing and next-day-only benefit is insufficient justification to displace
due-day service logic.

See `MANIFEST.json` for per-lane custody/disposition.

## Executed checks

```
python -B -m unittest -v test_planting_regime_gate.py
```

8/8 tests pass locally.  Covered: obligation preservation, fail-open evidence
handling, verified-loss rejection, break-even admission, collateral floors, and
same-crop mixed admit/reject cases proving there is no global crop ban.

No production/default/archive/Kaggle setting is changed by this package.
