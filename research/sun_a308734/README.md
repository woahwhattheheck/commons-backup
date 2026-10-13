# Sun A308734 low-obstruction atlas

Zhi-Wei Sun's OEIS [A308734](https://oeis.org/A308734) asks whether every integer `n > 1` has

```text
n = x^2 + y^2 + (2^a 3^b)^2 + (2^c 5^d)^2
```

with all six variables nonnegative. The current OEIS record advertises a **$2,500 first-correct-proof reward** and records verification through `1.6×10^11` (Jiao-Min Lin, 2022). Soumyarup Banerjee's 2024 *Journal of Number Theory* paper [On a conjecture of Sun about sums of restricted squares](https://doi.org/10.1016/j.jnt.2023.09.004) proves almost-prime relaxations; it does not prove the exact conjecture.

This directory is a proof-search reduction and exact verifier. **It is not a proof, counterexample, submission, sponsor contact, prize claim, or revenue claim.**

## Exact finite lemma landed here

Write the two restricted squares as

```text
u = 4^a 9^b,     v = 4^c 25^d.
```

Let

```text
P = 3·7·11·19·23·31·43·47 = 6,324,430,497.
```

The 20 explicit pairs in `residue_cover.py` have totals

```text
2, 5, 8, 10, 13, 17, 20, 25, 26, 29,
32, 34, 37, 40, 41, 52, 61, 65, 73, 85.
```

**Lemma (finite CRT cover).** For every integer `n`, at least one listed pair total `s=u+v` satisfies

```text
gcd(n - s, P) = 1.
```

Consequently, for every `n >= 85`, one of these 20 tiny choices makes the nonnegative residual `n-s` avoid the first eight possible sum-of-two-squares obstruction primes `p ≡ 3 (mod 4)`. Any remaining obstruction begins at `p=59` or above.

### Why the certificate is exact

For one prime `p` and residue `r=n mod p`, candidate `s` survives precisely when `r != s mod p`. `residue_cover.py` encodes the surviving candidates as a bitmask. It then intersects the masks over **every residue** of each of the eight primes. This is exhaustive CRT enumeration compressed by identical survivor states, not random sampling.

The reachable-mask counts after primes `3,7,11,19,23,31,43,47` are exactly

```text
3, 21, 181, 1507, 10746, 61553, 202209, 508812
```

and the minimum surviving candidate counts are

```text
10, 7, 6, 5, 4, 3, 2, 1.
```

The zero mask is never reachable. `test_residue_cover.py` also independently enumerates all `100,947` residues for the first five obstruction primes.

## Explicit overclaim fences

The finite lemma does **not** prove the residual is a sum of two squares. Fermat's two-square criterion still requires *every* prime `p ≡ 3 (mod 4)` to occur with even valuation.

Two exact counterexamples mark the current menu boundaries:

- The earlier 12-total menu covers through `p=31` but fails when `p=43` is added. At `n ≡ 99,162,274 (mod 134,562,351)`, every one of those 12 residuals shares a factor with `3·7·11·19·23·31·43`.
- The final 20-total menu covers through `p=47` but **does not** extend through `p=59`. At `n ≡ 41,144,806,933 (mod 373,141,399,323)`, every one of the 20 residuals shares at least one factor with the first nine obstruction primes.

The deterministic JSON certificate records the exact gcd row for both failures. These are counterexamples to stronger finite-menu lemmas, **not** counterexamples to A308734.

## Exact witness seam

`oracle.py` reuses the already-merged deterministic unsigned-64-bit sum-of-two-squares constructor from `research.sun_a303656.oracle`. `find_fixed_menu_witness(n)` tries only the 20 certified pairs and reconstructs all six A308734 variables when a residual is representable. A `None` result means only that this tiny menu did not work.

## Reproduce

From repository root:

```bash
python -m compileall -q research/sun_a308734
python -m unittest -q research.sun_a308734.test_residue_cover
python -O -m unittest -q research.sun_a308734.test_residue_cover
python -m research.sun_a308734.generate_evidence
sha256sum research/sun_a308734/evidence/low_obstruction_cover_v1.json
```

## Productive next proof work

The result exposes a sharper target than another broad finite search: prove that some bounded or structured family of restricted pairs controls **all** `3 mod 4` prime valuations, or combine this low-prime elimination with an analytic/descent argument that forces a two-square residual. The explicit `p=59` failure means simply appending more low primes to this fixed 20-term menu is not a proof strategy by itself.

## Sources

- [OEIS A308734](https://oeis.org/A308734)
- [Banerjee, *On a conjecture of Sun about sums of restricted squares*, JNT 256 (2024), 253-289](https://doi.org/10.1016/j.jnt.2023.09.004)
- [Sun, *Restricted sums of four squares*](https://doi.org/10.1142/S1793042119501045)
