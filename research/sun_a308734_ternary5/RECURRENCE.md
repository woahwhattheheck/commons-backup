# Bad-prime recurrence lattice on the exponent axes

Status: **proved structural lemma; not a proof of A308661.**

Let `N ≡ 5 (mod 12)` and

```text
m(a,b) = N - 4^a 25^b,   a >= 1, b >= 0.
```

For every positive residual, `m(a,b) ≡ 1 (mod 12)`. Define

```text
B(m) = {p prime : p ≡ 3 (mod 4), v_p(m) odd}.
```

Every failed two-square residual has nonempty `B(m)`; in fact its cardinality is even and at least two, and `3` never belongs to it.

## Proposition A — recurrence along the 5-exponent

Fix `a`. If a bad prime `p` belongs to both `B(m(a,b))` and `B(m(a,c))` with `b<c`, then

```text
ord_p(25) | (c-b),
```

and `ord_p(25)` is an odd integer at least 3.

### Proof

Because `p` divides both residuals, it divides their difference

```text
4^a 25^b (25^(c-b)-1).
```

A bad prime is odd and cannot be 5, so `25^(c-b) ≡ 1 (mod p)` and the multiplicative order divides `c-b`.

Since `p ≡ 3 (mod 4)`, `(p-1)/2` is odd. The element `25=5^2` is a quadratic residue modulo `p`, so its order divides the quadratic-residue subgroup order `(p-1)/2`; hence the order is odd.

The order cannot be 1: `25 ≡ 1 (mod p)` would imply `p | 24`, whose only prime divisor congruent to `3 mod 4` is `3`, while every residual is `1 mod 3`. Therefore the order is odd and at least 3. ∎

### Dyadic corollary

If `|c-b|` is any power of two, then

```text
B(m(a,b)) ∩ B(m(a,c)) = ∅.
```

No odd integer at least 3 divides a power of two. Thus the earlier `b,b+1,b+2` disjointness lemma is only the first finite shadow of an infinite restriction: **the same bad prime can never recur at dyadic separation on the 5-exponent axis.**

### First possible recurrence

At separation 3, any shared bad prime must divide

```text
25^3 - 1 = 15624 = 2^3 * 3^2 * 7 * 31.
```

Since 3 is excluded,

```text
B(m(a,b)) ∩ B(m(a,b+3)) ⊆ {7,31}.
```

So even the first legal recurrence distance is extremely rigid.

## Proposition B — recurrence along the 2-exponent

Fix `b`. If a bad prime `p` belongs to both `B(m(a,b))` and `B(m(c,b))` with `a<c`, then

```text
ord_p(4) | (c-a),
```

and `ord_p(4)` is odd and at least 3.

The proof is identical: `p` divides `4^(c-a)-1`; `4=2^2` is a quadratic residue; its order divides odd `(p-1)/2`; order 1 would force `p|3`, hence `p=3`, impossible for these residuals.

Therefore a bad prime also cannot recur at any power-of-two separation on the 2-exponent axis.

At separation 3,

```text
4^3 - 1 = 63 = 3^2 * 7,
```

so

```text
B(m(a,b)) ∩ B(m(a+3,b)) ⊆ {7}.
```

## Why this matters, and why it is not enough

A hypothetical counterexample to A308661 cannot keep one fixed local obstruction while moving through the admissible exponent lattice. Along either coordinate axis, every recurring bad prime is locked to a nontrivial **odd multiplicative-order period**; dyadic separations destroy recurrence completely.

This replaces an informal "new primes seem to appear" observation with an exact infinite recurrence law. It also identifies the correct next object for a proof attempt: the relation lattice of `4` and `25` inside the odd-order quadratic-residue subgroup modulo primes `p ≡ 3 (mod 4)`.

It still does not prove the conjecture. Different bad primes can appear at different exponent points, and primes with suitable odd order can recur at larger separations. A full proof must show that these permitted odd-period obstruction schedules cannot cover every positive residual (with odd valuation), or must obtain a separate descent/analytic/global-form argument.
