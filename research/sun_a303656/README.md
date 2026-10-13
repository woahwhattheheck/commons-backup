# Sun A303656 exact research harness

Zhi-Wei Sun's OEIS [A303656](https://oeis.org/A303656) conjectures that every
integer `n > 1` has

```text
n = a² + b² + 3ᶜ + 5ᵈ
```

for nonnegative integers `a,b,c,d`. The current OEIS record advertises a
**$3,500 first-proof prize** and records verification through `2.4×10¹¹`.
DeepMind's `formal-conjectures` repository carries the corresponding open Lean
statement at `FormalConjectures/OEIS/303656.lean`.

This directory contains a proof-search instrument and bounded analytic lemmas.
**It is not a proof or counterexample to A303656, a submission, or a prize claim.**
It gives future workers exact arithmetic and explicit limits on proposed routes.

## What is exact

`oracle.py` supplies a deterministic unsigned-64-bit pipeline:

- deterministic Miller-Rabin primality testing on `[0,2⁶⁴)`;
- deterministic Pollard-Brent factorization;
- the sum-of-two-squares criterion (every `p ≡ 3 mod 4` has even valuation);
- Cornacchia construction for primes `p ≡ 1 mod 4`;
- Gaussian multiplication to construct `a,b`, not merely decide existence;
- lexicographic search over `(c,d)` with exact witness reconstruction.

Every returned witness is checked by integer equality. Absence of a witness from
a finite search is never treated as a counterexample to the conjecture.

`factor_u64` accepts integers `1 <= n < 2^64`. It returns the empty
factorization `()` for `1` and raises `ValueError` for `0`, which has no prime
factorization. The separate sum-of-two-squares operation accepts zero and
returns `(0, 0)` before calling the factorization helper.

`modular.py` uses cyclic bitsets to compute, without sampling, the full residue
set

```text
{x²+y²+3ᶜ+5ᵈ mod m : x,y,c,d ≥ 0}
```

for a requested modulus. It also runs a deliberately limited CRT-cover
experiment: for each prime `p ≡ 3 mod 4`, select one residue `n mod p` and count
which exponent pairs satisfy `p | n-3ᶜ-5ᵈ`. Divisibility alone does **not** prove
odd valuation, and uncovered exponent pairs prevent a counterexample
certificate. The tool reports both limitations explicitly.

## Analytic local coverage and finite-offset limit

The [prime-power local-coverage note](PRIME_POWER_LOCAL_COVER.md) proves that
every residue modulo every prime power is represented even with exponents
`c,d in {0,1}`. For every target `n > 1` and each prime, one of the four offsets
`2,4,6,8` is at most `n` and works at every depth of that prime, with the same
exponent pair throughout. Thus an individual-prime obstruction search cannot
succeed even after bounding the restricted offset by the target.

The [dyadic palette bound](DYADIC_PALETTE_BOUND.md) proves that four is the
exact minimum for a fixed local-cover palette: any three integer offsets miss
an explicit class modulo a power of two, even when their sizes are unrestricted.

That same four-offset palette fails on an explicit composite CRT progression.
More generally, every fixed finite list of exact exponent pairs fails for
infinitely many positive integers. A composite-modulus argument must use one
compatible exponent pair across its components; prime-power solutions cannot
choose those exponents independently and then be joined by CRT.

These are elementary analytic lemmas, with full proofs and no new computation.
They do not settle unrestricted composite-modulus coverage or A303656. The
recorded finite evidence below remains unchanged.

## Current negative evidence

The deterministic receipt in `evidence/negative_evidence_v1.json` records:

- no missing residue for any modulus `2..500`;
- no missing residue for every `2,3,5,7,11`-smooth modulus at most `30,000`;
  together these form **1,151 exact modulus checks**;
- a one-residue-per-prime greedy cover on the `160×110` exponent grid using all
  **338** primes `p ≡ 3 mod 4`, `7 ≤ p < 5000`, which covers `13,226` of `17,600`
  pairs and leaves **4,374** uncovered;
- 250 seeded exact witnesses near each of `10⁹`, `10¹²`, `10¹⁵`, and `10¹⁸`.

Interpretation: the conjecture survives these tests, and neither a small local
obstruction nor this simple finite congruence-cover recipe closes the problem.
That is useful route-pruning, not theorem proof.

## Reproduce

From the repository root:

```bash
python -m compileall -q research/sun_a303656
python -m unittest -q research.sun_a303656.test_oracle
python -O -m unittest -q research.sun_a303656.test_oracle
python -m research.sun_a303656.generate_evidence
sha256sum research/sun_a303656/evidence/negative_evidence_v1.json
```

Find and verify one witness:

```bash
python -m research.sun_a303656.oracle 1000000000000000000
```

## Productive next attacks

1. Focus new residue-obstruction searches on composite moduli and shared
   exponent-pair compatibility; the analytic note proves full coverage for
   every individual prime power. Replace the ascending-prime greedy cover with
   an exact multiple-choice maximum-coverage or SAT model, including `p²`
   constraints that force odd valuation instead of mere divisibility.
2. Search for a finite covering on exponent *period classes*, not a bounded
   rectangle; only then can CRT produce a global candidate.
3. Seek a descent or induction identity that preserves exactly two unrestricted
   squares and one power of each base. Finite verification cannot substitute for
   this uniform step.
4. Test any claimed analytic route against the word **every**: density-one or
   almost-all representation theorems do not settle A303656.
5. Formalize only complete lemmas with explicit hypotheses; the public Lean file
   is currently a statement with `sorry`, not evidence of a proof.

## Sources

- [OEIS A303656](https://oeis.org/A303656)
- [Sun, *Restricted sums of four squares*](https://arxiv.org/abs/1701.05868)
- [Formal Conjectures statement](https://github.com/google-deepmind/formal-conjectures/blob/main/FormalConjectures/OEIS/303656.lean)
