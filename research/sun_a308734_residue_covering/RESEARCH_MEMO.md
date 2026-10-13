# Research memo — A308734 residue covering and proof barriers

## Target and source truth

Sun's conjecture asks whether every integer `n>1` has

`n = x^2 + y^2 + (2^a 3^b)^2 + (2^c 5^d)^2`

with all six variables nonnegative integers.  The current OEIS A308734 page
states the conjecture, records verification through `1.6*10^11`, and records
Sun's advertised US$2,500 reward for the first correct proof:
<https://oeis.org/A308734>.  Sun's original public question is at
<https://mathoverflow.net/questions/334474/four-square-conjecture>.

Banerjee's 2024 Journal of Number Theory paper studies this exact restricted
square direction with sieve theory and almost-prime relaxations:
<https://arxiv.org/abs/2202.04057>.  Its abstract describes progress toward
Sun's conjecture, not a proof of the exact pure `2^a3^b` / `2^c5^d` claim.
This memo therefore treats A308734 as open and keeps every finite computation
below an explicit evidence ceiling.

## Lemma 1 — 4-adic lifting reduces the proof to `4 ∤ n`

Suppose

`m = x^2 + y^2 + (2^a3^b)^2 + (2^c5^d)^2`.

Then for every `q>=0`,

`4^q m = (2^q x)^2 + (2^q y)^2
        + (2^(a+q)3^b)^2 + (2^(c+q)5^d)^2`.

Hence, writing any positive `n` uniquely as `n=4^q m` with `4 ∤ m`, a proof
for the primitive core `m` lifts mechanically to `n`.  The implementation's
`four_adic_core`, `lift_witness_by_four`, and hostile round-trip tests check
this identity but the argument itself is exact and computation-independent.

**Consequence:** proof search can focus on `n ≡ 1,2,3 (mod 4)`.

## Lemma 2 — exact finite local cover for the first five obstruction primes

Write

`S(a,b,c,d) = 4^a 9^b + 4^c 25^d`.

Taking `a,b,c,d ∈ {0,1}` gives 15 distinct shifts:

`{2,5,8,10,13,26,29,34,37,40,61,101,104,109,136}`.

For a prime `p ≡ 3 (mod 4)`, a sum of two squares cannot have `p` to an odd
valuation.  Modulo `p^2`, the case `v_p(n-S)=1` is exactly detectable:
`n-S` is a nonzero multiple of `p` modulo `p^2`.

For each selected prime and each residue `r mod p^2`, the verifier forms a
bit mask of the 15 shifts killed by `v_p(r-S)=1`.  Inclusion-dominated masks
are discarded.  The remaining maximal-mask counts are:

| p | maximal bad masks |
|---:|---:|
| 3 | 6 |
| 7 | 6 |
| 11 | 8 |
| 19 | 13 |
| 23 | 14 |

If some integer `n` killed every candidate at at least one selected prime,
then the tuple `(n mod p^2)_p` would choose one local bad mask per prime whose
union contains all 15 candidates.  Conversely, because the `p^2` moduli are
pairwise coprime, CRT realizes every tuple of local residues.  Exhaustively
checking the finite maximal-mask product therefore proves the exact local
statement:

> For every integer `n`, at least one of the 15 shifts has
> `v_p(n-S) != 1` for every `p ∈ {3,7,11,19,23}`.

`certificate.json` contains all maximal masks and residue witnesses.  The
verifier regenerates them from raw exponents rather than trusting the file.
Canonical payload SHA-256:
`841b45dce6e03c049ba4de0ebe4baff3eee88ef9ce57110edde0a50c20d18189`.

### What Lemma 2 does *not* say

It does not exclude `v_p=3,5,...` when `n-S ≡ 0 (mod p^2)`.  It says nothing
about primes `p ≡ 3 (mod 4)` outside the five-prime band.  It does not even
assert `n-S>=0`.  Therefore it is a finite local non-obstruction lemma only,
not a representation theorem.

## Proposition 3 — any fixed finite shift strategy is globally impossible

This is the strongest structural result from this lane.

Let `F={s_1,...,s_k}` be any fixed finite set of distinct integer shifts.
Choose distinct primes `p_i ≡ 3 (mod 4)`.  Impose the simultaneous
congruences

`n ≡ s_i + p_i (mod p_i^2)` for `i=1,...,k`.

CRT gives a residue class modulo `M=∏ p_i^2`.  Every sufficiently large
positive representative of that class satisfies

`n-s_i ≡ p_i (mod p_i^2)`, hence `v_{p_i}(n-s_i)=1`.

By the two-square theorem, no `n-s_i` is a sum of two squares.  There are
infinitely many such `n` because the entire arithmetic progression modulo
`M` works.

**Therefore no proof of A308734 can freeze a finite list of exponent tuples
and hope that one of their remainders is always a sum of two squares.**  A
successful two-square-remainder strategy must exploit the set of allowable
smooth shifts growing with `n`, or introduce a materially different global
argument.

`fixed_shift_crt_killer()` constructs this obstruction for any proposed
finite list and tests every assigned `p_i` valuation directly.  For the 15
small shifts above it uses the first 15 primes `3 mod 4` and emits a
47-decimal-digit CRT modulus/residue class.  That concrete giant integer is
an illustration; the proposition is symbolic and does not depend on it.

This proposition also explains why extending finite local certificates prime
by prime is not a path to a complete proof: any fixed candidate list can
always be defeated once enough fresh obstruction primes are admitted.

## Negative result A — the five-prime certificate does not extend to 31

For the same 15 shifts, adding `p=31` makes a full local adversary possible.
The deterministic verifier currently finds local residues

- `n ≡ 4 (mod 3^2)`
- `n ≡ 19 (mod 7^2)`
- `n ≡ 24 (mod 11^2)`
- `n ≡ 48 (mod 19^2)`
- `n ≡ 31 (mod 23^2)`
- `n ≡ 11 (mod 31^2)`

with CRT representative
`6,743,801,877,034 mod 9,792,875,233,449`.
For every one of the 15 shifts, at least one of these six primes then appears
to exact valuation 1 in the residual.  `probe-extension 31` independently
recomputes and validates this witness.

This refutes only the stronger *small-family six-prime local-cover* claim.
It is not a counterexample to Sun because larger exponents yield additional
shifts.

## Negative result B — local cover is not global two-square coverage

A bounded hostile scout checks the stronger hypothesis that one of the same
15 small shifts always leaves an actual sum of two squares.  After removing
multiples of four by Lemma 1, its first failure through 1000 is `n=499`.
No one of the 15 residuals is a sum of two squares.

But 499 itself obeys Sun:

`499 = 11^2 + 19^2 + (2^0 3^0)^2 + (2^2 5^0)^2
     = 121 + 361 + 1 + 16`.

So the failure is useful: a larger exponent (`c=2`) repairs the candidate.
It is a direct guard against confusing a finite local certificate with the
conjecture.

## Where the real proof difficulty remains

For a chosen smooth shift `S`, Fermat's two-square criterion asks that **all**
primes `p ≡ 3 (mod 4)` occur to even valuation in `n-S`.  The finite mask
engine can certify absence of selected local obstructions and can kill false
covering lemmas, but a complete proof needs a global mechanism over an
unbounded family of shifts.

The most plausible next analytic target is therefore not "add more fixed
shifts."  It is to quantify how the growing family

`F(n) = {4^a9^b + 4^c25^d <= n}`

is distributed modulo obstruction prime powers, and prove that at least one
member survives the simultaneous two-square conditions.  The local engine
is useful here as a singular-series / local-solubility sanity check for any
proposed sieve or density lemma.  Banerjee's sieve-theoretic almost-prime
progress is the natural literature anchor for this step.

Concrete next subproblems for the swarm:

1. **Growing-family density lemma.** Bound, uniformly enough in `n`, how many
   available smooth shifts are killed by `v_p(n-S)` odd for each
   `p ≡ 3 (mod 4)`.  Fixed-family CRT shows the growth with `n` is essential.
2. **Prime-power depth.** Upgrade `p^2` masks to `p^k` and track odd
   valuations `1,3,...<k`; use the verifier to test any claimed uniform
   density bound before attempting proof.
3. **Sieve bridge.** Reconcile the exact pure smooth target with Banerjee's
   almost-prime sieve output; identify precisely what estimate would force
   the residual auxiliary factors to disappear rather than merely have few
   prime factors.
4. **Primitive-case structure.** Because 4-adic lifting is exact, formulate
   all analytic estimates on `4 ∤ n`; do not spend proof effort repeatedly
   re-solving the scaled cases.
5. **Independent proof review before payout.** No sponsor contact should be
   made until a complete proof survives a separate verifier/reviewer lane.

## Evidence status

- 4-adic lifting: **RIGOROUS SYMBOLIC LEMMA**.
- Five-prime 15-shift local cover: **RIGOROUS FINITE CERTIFICATE**.
- Fixed-finite-family CRT barrier: **RIGOROUS SYMBOLIC PROPOSITION**.
- `p=31` extension failure: **RIGOROUS FINITE COUNTERCERTIFICATE**.
- `n=499` small-family failure and larger-exponent repair: **EXACT BOUNDED
  COMPUTATIONAL RESULT**.
- A308734 itself: **OPEN / NOT PROVED HERE**.
- Prize/payment/revenue: **NOT CLAIMED**.
