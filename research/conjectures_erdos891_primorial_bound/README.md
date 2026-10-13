# Erdős 891: primorial lower bound for any admissible witness

This directory records one reusable first structural fact for the Conjectures.io target
`Erdos891.erdos_891`. It does **not** solve Erdős 891.

## Exact sponsor target

Fresh sponsor metadata read on 2026-09-18:

- task: `fc-8432eac9-erdos891-erdos-891-f7c029a9da-formalized-v1`
- commitment: `sha256:f27b7e330416cb7906fe33072ed51ac3014c29e6ca3b8d66cba9338147745501`
- source-type SHA-256: `3114dca122af84199da3e5a5680ee5f110455c698328c16ce9954ae0f4de74de`
- rendered direct proposition:

```text
True ↔ ∀ k ≥ 2, ∀ᶠ (n : ℕ) in Filter.atTop,
  ∃ m ∈ Finset.Ico n
      (n + ∏ i ∈ Finset.range k, Nat.nth Nat.Prime i),
    k < ArithmeticFunction.cardDistinctFactors m
```

The public Formal Conjectures source currently writes the same open problem using the scoped notation
`ω m` for `ArithmeticFunction.cardDistinctFactors m`. It also records that the case `k = 2`
(intervals of length `6`) remains open.

## The structural lemma

Write

```text
P_r = p_1 p_2 ... p_r,
```

where `2 = p_1 < p_2 < ...` are the primes and `P_0 = 1`.

> **Primorial lower bound.** If `m > 0` has exactly `r` distinct prime factors, then
> `P_r ≤ m`. Consequently, if `k < ω(m)`, then `P_(k+1) ≤ m`.

This bound is sharp: equality holds at `m = P_r`.

For the Erdős 891 target, every witness to `k < ω(m)` is therefore automatically at least the
next primorial `P_(k+1)`. Examples:

| target `k` | minimum possible witness from factor count alone |
| ---: | ---: |
| 2 | 30 |
| 3 | 210 |
| 4 | 2,310 |
| 5 | 30,030 |
| 6 | 510,510 |
| 7 | 9,699,690 |
| 8 | 223,092,870 |
| 9 | 6,469,693,230 |
| 10 | 200,560,490,130 |

It is a constraint on every eventual witness, not an existence theorem for witnesses inside the
short interval. The difficult distributional part of Erdős 891 remains untouched.

## Proof

Let the distinct prime divisors of positive `m` be

```text
q_1 < q_2 < ... < q_r.
```

Because `p_i` is the `i`-th smallest prime globally, `p_i ≤ q_i` for every `1 ≤ i ≤ r`. Hence

```text
P_r = ∏ p_i ≤ ∏ q_i.
```

The product `∏ q_i` is the radical of `m`: it divides `m`. Since `m > 0`, divisibility gives
`∏ q_i ≤ m`. Chaining the two inequalities yields `P_r ≤ m`.

If `k < ω(m)`, then `r = ω(m) ≥ k+1`. Primorials are increasing, so
`P_(k+1) ≤ P_r ≤ m`.

Sharpness follows because `P_r` itself is squarefree with exactly `r` distinct prime factors.

## Exact executable regression

`primorial_bound.py` provides a dependency-free independent finite oracle. The published receipt
checks every integer `1 ≤ m ≤ 1,000,000`.

For each `m` it computes `ω(m)` by an exact sieve and checks

```text
P_(ω(m)) ≤ m.
```

It additionally verifies that the first occurrence of each factor-count `r` seen in the scan is
exactly `P_r`. The scan reaches `r = 7`, so it independently recovers the sharp minima

```text
1, 2, 6, 30, 210, 2310, 30030, 510510.
```

Published exact receipt values:

```text
cases_checked = 1,000,000
max_distinct_prime_factors_seen = 7
records_sha256 = a149278e80734e40ecd0961181cfb546418a72a74dfa3665d015106284069736
payload_sha256 = aee333e698cd40436e4c8967adb217fe4a34009d8ee01034fd25a78b63002025
receipt_file_sha256 = 8a8cc437c6d48d6efb210d0d6ac16cd37b645b38704e95fb239c71b464afe7c5
```

Validation before publication:

```text
python3 -m py_compile primorial_bound.py test_primorial_bound.py     PASS
python3 -m unittest -v test_primorial_bound.py                       8/8 PASS
python3 -O -m unittest -v test_primorial_bound.py                    8/8 PASS
python3 primorial_bound.py --limit 1000000 --max-r 13 --pretty \
  --write-receipt receipt.json                                       PASS
```

## Evidence ceiling

The displayed primorial inequality has a complete ordinary mathematical proof above, and the
finite oracle is an exact regression of one million cases. This environment has not supplied a
Lean-kernel elaboration receipt for the general theorem, and this carrier makes no claim of a
sponsor-accepted contribution, solved conjecture, bounty, payment, or revenue.

See `LEAN_HANDOFF.md` for a minimal formalization plan that deliberately reuses Mathlib's
`Nat.primeFactors` / radical machinery rather than encoding a new factorization theory.
