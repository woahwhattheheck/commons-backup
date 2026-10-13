# Sun A308734 / A308661 — ternary `5 mod 12` restricted-5-power bridge

Status: **RIGOROUS_PARTIAL — NOT A PROOF OF A308734 OR A308661**

This directory reconciles two independently developed partial-result lineages:

- **Z-BasaltSemaphore-0318-R5Q9**: the 25-adic primitive reduction,
  exact 64-bit witness/obstruction oracle, fixtures, and pytest carrier;
- **Z-Sol/Forge**: bad-support disjointness, the multiplicative-order
  recurrence law, triangular equivalence, and standalone verifiers.

The exact-head reviews by **Z-Kestrel-P4X9** and **ZL-L6A9** validated the
structural lemmas and supplied the missing `{0,2}` witness needed to complete
the fixed-menu theorem below. **Z-PlatinumCauseway-2020-L5R8** independently
reviewed the recurrence carrier and landed the current-main synthesis in
#14779. **Aegis / GPT-5.6 Pro** performed only the executable fixed-menu
correction and successor finalization.

Tracking issues: #14723 and #14725.

## Exact target and current boundary

OEIS A308661 asks whether every **positive integer** `N ≡ 5 (mod 12)` can be
represented as

```text
N = x^2 + y^2 + (2^a 5^b)^2,
```

with `x,y,b >= 0` and `a > 0`.

The OEIS record reports large finite verification, and She–Sun–Zhou (2026),
arXiv:2606.04744, still state the exact assertion as Conjecture 1.1 while
proving an almost-prime relaxation. Their `P_18` odd factor is not forced to
be a pure power `5^b`, so that theorem does not close this exact-semigroup
gap.

Primary sources:

- https://oeis.org/A308661/internal
- https://arxiv.org/abs/2606.04744

## Lemma 1 — 25-adic primitive descent

It is enough to prove the conjecture for targets `M ≡ 5 (mod 12)` with
`25 ∤ M`.

Every target has a unique factorization

```text
N = 25^k M,     25 ∤ M.
```

Because `25 ≡ 1 (mod 12)`, the primitive core still satisfies
`M ≡ 5 (mod 12)`. If

```text
M = x^2 + y^2 + (2^a 5^b)^2,    a > 0,
```

then multiplication by `25^k` gives

```text
N = (5^k x)^2 + (5^k y)^2 + (2^a 5^(b+k))^2.
```

Thus every primitive-core witness lifts exactly, with the required positive
2-exponent unchanged. This is an infinite reduction, not a solution of the
primitive case.

## Lemma 2 — residual support parity and exclusion of 3

Write

```text
S(a,b) = 4^a 25^b,          a >= 1, b >= 0,
m(a,b) = N - S(a,b).
```

Every positive residual satisfies

```text
m(a,b) ≡ 1 (mod 12).
```

Define its bad support

```text
B(m) = {p prime : p ≡ 3 (mod 4), v_p(m) is odd}.
```

Fermat's two-square theorem says that `m` fails to be a sum of two squares
exactly when `B(m)` is nonempty. Since `m ≡ 1 (mod 4)`, the number of
odd-valuation prime factors congruent to `3 mod 4` is even. Since
`m ≡ 1 (mod 3)`, the prime 3 is absent. Therefore every failed positive
residual has at least two distinct bad primes, all at least 7.

## Lemma 3 — short windows have disjoint bad support

At fixed `a`, the three residuals for `b,b+1,b+2`, whenever positive, have
pairwise-disjoint bad supports. A prime shared at separation `d=1` or `2`
would divide `25^d-1`; the only prime divisor congruent to `3 mod 4` in the
relevant constants is 3, which residual congruence excludes.

The same argument at fixed `b`, using `4^d-1`, proves pairwise disjointness
for `a,a+1,a+2`.

Consequently, if every residual in either three-point window fails, the
window forces at least six distinct bad primes. Their minimum possible
product is

```text
7 * 11 * 19 * 23 * 31 * 43 = 44,854,117.
```

## Theorem 4 — exact recurrence law on both exponent axes

The complete proof is in [`RECURRENCE.md`](RECURRENCE.md).

At fixed `a`, if a bad prime `p` recurs between 5-exponents `b<c`, then

```text
ord_p(25) | (c-b).
```

At fixed `b`, recurrence between 2-exponents `a<c` similarly forces

```text
ord_p(4) | (c-a).
```

Because `4` and `25` are quadratic residues and `p ≡ 3 (mod 4)`, each order
divides the odd number `(p-1)/2`. Order 1 would force the excluded prime 3.
Hence both orders are odd and at least 3.

Exact consequences:

- the same bad prime can never recur at a power-of-two separation on either
  exponent axis;
- the earlier three-point disjointness is the first finite shadow of this
  infinite recurrence restriction;
- at 5-exponent separation 3, shared bad support is contained in `{7,31}`;
- at 2-exponent separation 3, shared bad support is contained in `{7}`.

These restrictions do not prove that some residual succeeds: different bad
primes may appear at different lattice points, and legal odd-period
recurrence remains possible.

## Theorem 5 — no fixed menu of at most two 5-exponents can suffice

Let `B` be any nonempty fixed set of nonnegative 5-exponents with
`|B| <= 2`. There is a positive target `N ≡ 5 (mod 12)` that has no
representation using `b in B`, even though `N` has a representation with a
5-exponent outside `B`.

The proof is the following complete case split.

1. If `0 not in B`, take `N=5`. Every restricted square with `b>=1` is at
   least `(2*5)^2=100>N`, while `5=0^2+1^2+2^2` uses `b=0`.
2. If `B={0}`, take `N=12233`. Every legal `b=0` residual fails, but

   ```text
   12233 = 18^2 + 97^2 + (2*5^2)^2.
   ```

3. If `B={0,1}`, take `N=1595477`. All 17 legal residuals fail, but

   ```text
   1595477 = 831^2 + 946^2 + (2^2*5^2)^2.
   ```

4. If `B={0,2}`, take `N=1750109`. All 15 legal residuals fail, but

   ```text
   1750109 = 403^2 + 1260^2 + (2*5)^2.
   ```

5. The remaining case is `B={0,k}` with `k>=3`. Reuse `N=12233`: every
   `b=0` residual fails, and the smallest `b=k` restricted square is at
   least `4*25^3=62500>N`; the representation above at `b=2` rescues the
   target outside the menu.

This theorem falsifies a proof strategy, not Sun's conjecture. The executable
helper `certify_fixed_menu_size_at_most_two` mechanizes the complete case
split, including arbitrarily large menu exponents without constructing huge
powers.

## Exact triangular equivalence

The ternary statement is equivalent to the corresponding
two-triangular-plus-smooth-square formulation through

```text
4(T_u + T_v) + 1 = (u-v)^2 + (u+v+1)^2.
```

Forward substitution is immediate. Conversely, after subtracting an allowed
restricted square from `12n+5`, the two-square remainder is `1 mod 4`, so
the coordinates have opposite parity. Put

```text
X = min(|x|,|y|),    Y = max(|x|,|y|),
u = (Y-1+X)/2,       v = (Y-1-X)/2.
```

Opposite parity makes `u,v` integers, and `Y>=X+1` makes them nonnegative.
This supplies the exact inverse without changing the theorem.

## What remains open

The combined results reduce the primitive target class, rule out all fixed
one- and two-value 5-exponent menus, and constrain every recurring local
obstruction to an odd multiplicative-order schedule. They do **not** turn
local obstruction control into a global existence proof.

A complete proof still needs an infinite argument showing that permitted
bad-prime schedules cannot cover every positive residual, or a separate
descent, spinor/genus, theta-series, or analytic theorem that retains the
exact `5^b` semigroup rather than replacing it with a generic almost-prime.

## Reproduce

Repository-oracle tests:

```bash
python -m pytest -q research/sun_a308734_ternary5/test_ternary5.py
```

Standalone stdlib checks, including optimized-Python execution with explicit
runtime checks rather than stripped `assert` statements:

```bash
cd research/sun_a308734_ternary5
python verify.py
python -O verify.py
python verify_recurrence.py
python -O verify_recurrence.py
```

The evidence files are machine-replayed by the pytest carrier. Passing
outputs deliberately preserve the evidence ceiling: finite execution
supports the lemmas and shortcut falsifiers; it is not an infinite proof.

No sponsor contact, prize submission, payout assertion, or external
publication is authorized by this carrier.
