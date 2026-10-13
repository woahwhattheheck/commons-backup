# Erdős 366 exact witness-search lane

This directory is the durable research artifact for Commons issue #15996 and lane
`CONJECTURES-ERDOS366-WITNESS-SEARCH-ZSOL-20260918`.

## Exact paid target

Conjectures.io's canonical Erdős 366 page was re-read on 2026-09-18 before the
lane was claimed. At that snapshot it displayed **$3,992**, "nobody has
started", and no proof or counterexample attempts.

The exact published Lean type is:

```lean
True ↔ ∃ n > 0, Nat.Full 2 n ∧ Nat.Full 3 (n + 1)
```

This orientation matters. The familiar `(8, 9)` and `(12167, 12168)` examples
run in the opposite 3-full → 2-full direction; they do not satisfy the target
because their successors have a prime with exponent exactly 2.

Pinned task identity:

- task id: `fc-8432eac9-erdos366-erdos-366-e013583642-formalized-v1`
- task commitment: `sha256:bdc4fc9e24b0984b86699ded1d2c0f00fe0fb9faf8ab48f374224e5a3790cc1a`
- source type hash: `sha256:6756a198d091e0d0a2c6913ee1de0c5eaf403a0f98873b7645b3c4337e162a99`
- observed `conjectures-io/conjectures-tasks` snapshot:
  `d9a67b509c5a8b220ba262c1c7ce26f61f52763a`
- manifest's formal-source repository commit:
  `8432eac998110a563e03df65a28c117e97c8c142`

The task manifest forbids using `Erdos366.erdos_366` itself as a dependency and
marks the task production-eligible.

## New interval result (2026-10-05)

The [fresh-range report](RANGE_1E12_2E12.md) covers every 3-full successor
in `10^12 < m <= 2*10^12`: **11,077 candidates and 0 target witnesses**.
The new [coefficient-plan/shard API](erdos366_range_shards.cjs) generates only
that interval. Its [saved manifest](range_1e12_2e12_manifest.json) identifies
the declared input, once-built plan and every candidate certificate across four
completed shards. The report gives the enumeration and predecessor-certificate
proofs, inherited prime-prefix premise and finite scope; the earlier search and
test evidence below retain their original scope.

## Search strategy

Write `m = n + 1`. Any target witness must have `m` 3-full, so instead of
scanning all integers the engine enumerates every 3-full `m ≤ B` directly from
its prime factorization:

```text
m = p1^e1 · ... · pr^er,  p1 < ... < pr,  each ei ≥ 3.
```

That representation is unique. The recursive enumerator chooses primes in
strictly increasing order and every exponent from 3 upward while the product
remains in range. Therefore every 3-full successor in the declared finite
range is visited exactly once.

For each enumerated `m`, the engine tests `n=m-1` for 2-fullness by exact trial
division using all primes through `sqrt(B)`. The common rejection path records
a prime with exponent 1. A surviving candidate is returned with complete
factorizations of both sides.

This makes the *bounded* search exhaustive. It does **not** turn a finite
negative computation into a proof that no global witness exists.

## Reproducible result

Command:

```bash
python research/math-prize-lab/erdos366/erdos366_search.py \
  --bound 1000000000000 --oeis-baseline --pretty
```

Result committed in `receipt_1e12.json`:

- inclusive successor bound `n+1 ≤ 10^12`;
- **41,135** 3-full successors enumerated;
- **0** target witnesses;
- deterministic per-candidate record digest
  `sha256:918602c8e3953bc30aa073be61f54fa3dd41ea77bf23709714747da9e5c5b437`;
- search-engine Git blob `7e9adb5c2b532a333df34495727e5728925ad746`;
- test-file Git blob `c3f3260d2521176e87beba37e6e1ca66780f0c36`.

This bounded result is an independent reproducibility receipt, not a novelty
claim and not an improvement over literature-scale searches reported around
this problem.

## OEIS orientation guard

OEIS A060355 lists starts of consecutive powerful pairs. The artifact embeds
the first 39 listed starts only as a regression baseline. For every listed
successor it verifies a concrete prime `p` with `p^2 || (n+1)`, which is enough
to prove that successor is **not** 3-full. The row digest is:

`sha256:519beda75bbeda694ca5df30c1f6229b78d6622d643ce8c19f859387497c9051`

This check deliberately does **not** claim the OEIS list is complete below any
bound.

## Tests

```bash
python -m unittest -v research/math-prize-lab/erdos366/test_erdos366_search.py
```

Six tests pass from the repository root in normal Python and real `python -O` after the import-bootstrap repair. They include:

- exact integer-root checks;
- generator equality against an independent brute-force oracle for 2-full and
  3-full numbers through 20,000;
- factorization-product checks;
- orientation regressions for 8/9 and 12167/12168;
- whole-search equality against brute force through 100,000;
- all 39 embedded OEIS successor obstruction checks.

## What this does and does not establish

Established computationally by this artifact: no witness with
`n+1 ≤ 10^12`, under the exact elementary arithmetic implemented and
cross-checked by the tests.

Not established: global nonexistence, a new theorem, or sponsor acceptance.
No paid verification attempt, wallet spend, sponsor submission, reward claim,
or booked revenue was made from this result.

The next useful escalation is not another naive scan from 1. It is a sharded
coefficient/residue search that can extend materially beyond known literature
baselines, while retaining exact factorization certificates. If a candidate
ever survives, the next gate is a proof against the pinned Lean task followed
by the sponsor's free preflight before any paid verification.
