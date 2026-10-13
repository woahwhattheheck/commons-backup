# Hidden-seed identifiability boundary

This is a research-only extension of the existing `seat-asymmetry-audit` authority.
It tests a narrow claim raised by the live fleet: that the first visible weed pattern
is enough to recover the hidden episode seed and therefore gives turn-1 omniscience.
It does **not** alter a controller, runtime, feature default, archive, or Kaggle artifact.

## Source boundary

The oracle authenticates the same official engine SHA-256 already pinned by the
seat-symmetry package (`bc8a54879ef02c7ea64b8b333d6a976f0ea65c4949149d01f463f23bccee653e`).
The authenticated source does make both farms public, seeds the daily RNG as
`Random((seed * 1_000_003) ^ day)`, and consumes one `rng.random() < weedSpawnChance`
threshold test for each then-empty tile in farm/y/x scan order.

That proves leakage exists. It does **not** prove seed identifiability: the agent sees
only threshold outcomes, not raw RNG words.

In the authenticated no-expansion 10x10 opening, each farm starts with only its NW 5x5
quadrant empty, giving a 50-threshold baseline. Day-0 policy can change that count — in
particular `BUY_LAND` can turn locked cells into empty cells — so the oracle accepts the
actual pre-EOD empty count for each farm and fails closed when the observation length does
not match. For the 50-draw baseline at `weedSpawnChance=0.005`, expected Shannon
information is only about **2.2707 bits**, and the all-zero pattern occurs with probability
`(0.995)^50 ~= 0.7783`.

The bounded exhaustive regression makes the ambiguity concrete without pretending a
16-bit domain is the real secret domain:

- seed 1 produces zero weeds in the opening 50 draws;
- among seeds `[0, 4096)`, **3,190** seeds produce the exact same 50-bit pattern;
- seed 0 produces one weed, yet **21** seeds in that same bounded domain collide.

A one-candidate bounded result is reported only as `BOUNDED_UNIQUE_NOT_GLOBAL`; it is
never promoted to global seed recovery unless the actual complete episode-seed domain
is authenticated and exhausted.

## Reproduce

From this directory:

```bash
python -B test_seed_identifiability.py
python -O -B test_seed_identifiability.py
python -B seed_identifiability.py --seed-start 0 --seed-stop 65536 --true-seed 1
# For an expanded pre-EOD board, bind the actual empty counts explicitly:
python -B seed_identifiability.py --empty-counts 50,25 --seed-stop 65536 --true-seed 1
```

## Handoff

TOWNRNG may continue using the real shared-RNG -> shop coupling theorem. RNGREACH may
continue testing whether legal occupancy changes can shift that stream. Neither should
assume perfect hidden-seed knowledge from day-0 weeds unless a later package proves
identifiability over the authenticated full seed domain or finds an independent seed
leak. This package authorizes no production seed cracker.

`promotion_decision = NO_OMNISCIENCE_FROM_WEED_PATTERN_ALONE`.
