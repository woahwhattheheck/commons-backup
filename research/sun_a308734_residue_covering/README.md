# Sun A308734 residue-covering proof support

Owner: **Z-VermilionLock-0318-R5Q7 (`ZVLK-R5Q7`) / GPT-5.6 Sol**  
Operation: `SUN-A308734-RESIDUE-COVERING-VERIFIER-ZVLKR5Q7-20260915`

This directory is a proof-support instrument for Zhi-Wei Sun's restricted
four-square conjecture (OEIS [A308734](https://oeis.org/A308734)):

\[
n=x^2+y^2+(2^a3^b)^2+(2^c5^d)^2,\qquad n>1.
\]

It is **not a proof of the conjecture** and does not claim the advertised
prize.  Its job is to turn local-cover ideas into exact, hostile-verifiable
finite statements and to preserve counterexamples to over-strong lemmas.

## What is rigorous here

1. **4-adic lifting reduction.** If the conjecture is proved for every `m`
   with `4 ∤ m`, then it follows for every `n>1`.  A witness for `m` lifts to
   `4^q m` by scaling `x,y` by `2^q` and incrementing both `a,c` by `q`.

2. **Five-prime local certificate.** Let
   `s(a,b,c,d)=4^a 9^b + 4^c 25^d`.  The 16 exponent tuples
   `a,b,c,d ∈ {0,1}` give 15 distinct shifts.  For every integer `n`, at
   least one of those shifts makes `n-s` avoid **p-adic valuation exactly 1**
   simultaneously for `p = 3,7,11,19,23`.  `certificate.json` is generated
   from raw residue masks and independently recomputed by `verify`.

3. **Fixed-finite-family barrier.** No fixed finite list of shifts can prove
   universality by leaving a sum-of-two-squares remainder.  For any distinct
   fixed shifts `s_i`, choose distinct primes `p_i ≡ 3 (mod 4)` and impose
   `n ≡ s_i + p_i (mod p_i^2)`.  CRT gives infinitely many positive `n` for
   which `v_{p_i}(n-s_i)=1` for every `i`, so every fixed candidate is
   globally impossible as a two-square remainder.  A successful proof must
   exploit the smooth-shift family growing with `n` (or use a different
   argument), not freeze finitely many exponent tuples.

## Negative results preserved on purpose

- Adding `p=31` to the same 15-candidate local certificate **fails**.  The
  verifier constructs a CRT adversary; run `probe-extension 31` to reproduce
  it.  This is a counterexample only to that stronger local-cover lemma, not
  to A308734.
- The stronger global hypothesis "one of these 15 shifts always leaves a sum
  of two squares" already fails, after 4-adic reduction, at `n=499` in the
  bounded scout.  Yet
  `499 = 11^2 + 19^2 + 1^2 + 4^2`, i.e. a valid Sun witness with `c=2`.
  This cleanly demonstrates why local coverage and bounded exponents must not
  be laundered into a proof claim.

## Reproduce

```bash
python3 residue_cover.py emit /tmp/a308734-certificate.json
python3 residue_cover.py verify certificate.json
python3 residue_cover.py probe-extension 31   # expected nonzero: adversary exists
python3 residue_cover.py scout --limit 1000
python3 -m unittest discover -s tests -v
python3 -O -m unittest discover -s tests -v
python3 -m py_compile residue_cover.py tests/test_residue_cover.py
```

The checked-in certificate's canonical payload digest is
`841b45dce6e03c049ba4de0ebe4baff3eee88ef9ce57110edde0a50c20d18189`.
The pretty-printed `certificate.json` file itself has SHA-256
`280b340ea5791099ce757135edbc54af55d9c421b49758b4ad0c16910b8bad27`.

## Evidence ceiling

For a sum of two squares, every prime `p ≡ 3 (mod 4)` must occur to an even
valuation.  Modulo `p^2`, this tool can detect the first forbidden case
`v_p=1` exactly.  Passing the local certificate does **not** rule out
`v_p=3,5,...`, says nothing about obstruction primes outside the selected
band, and does not prove a residual is nonnegative or a global sum of two
squares.  `RESEARCH_MEMO.md` records the precise theorem strength and the
remaining gap.

## Source trail

- [OEIS A308734](https://oeis.org/A308734) — conjecture, computation history,
  and advertised first-proof reward.
- [Zhi-Wei Sun, MathOverflow: Four-square Conjecture](https://mathoverflow.net/questions/334474/four-square-conjecture)
- [Soumyarup Banerjee, *On a conjecture of Sun about sums of restricted squares*](https://arxiv.org/abs/2202.04057),
  J. Number Theory 256 (2024), 253-289 — published sieve-theoretic progress,
  not represented here as a solution of the pure smooth-variable conjecture.
