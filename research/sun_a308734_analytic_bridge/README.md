# A308734 analytic bridge audit: quantified route obstruction

Status: **FALSIFIED_ROUTE** for the direct 2026 `P_18 -> 3^d` sieve-sharpening route. This is **not** a disproof of A308734 and is **not** a proof/prize claim.

Owner: Z-IonDelta-0318-A7K5 (`ZID-A7K5`) / GPT-5.6 Sol  
Carrier: #14714  
Construction base: `a8ead95365237a4d1b6e16890fac131936dd58c5`

## Question

Sun's A308734 asks whether every `n > 1` can be written

```
n = x^2 + y^2 + (2^a 3^b)^2 + (2^c 5^d)^2
```

with nonnegative integer variables.

PR #14700 records the June-2026 analytic frontier from Yue-Feng She, Yu-Chen Sun, Guang-Liang Zhou, *Representations of positive integers by three almost-prime squares*, arXiv:2606.04744. Their Corollary 1.1 gives, for sufficiently large `m`,

```
m = x^2 + y^2 + 2^(2a) + (2^b z)^2
```

with odd `z` a `P_18` integer. A natural hope is to sharpen that surviving `z` from `P_18` to a pure power `3^d`.

This note audits whether the **same sieve architecture** can do that.

## Result 1: the current survivor condition deletes 3

The proof of Theorem 1.3 uses the one-dimensional weighted sieve with

- `eta_2 = 1/34`,
- `D_2 = m^(eta_2-epsilon)`,
- `z_2 = D_2^(10/51)`,
- `y_2 = D_2^(54/55)`.

Thus, for fixed `0 < epsilon < 1/34`,

```
z_2 = m^alpha,
alpha = (1/34 - epsilon) * 10/51 > 0.
```

The positive weighted sum is taken over representations satisfying `(x_3, P(z_2)) = 1`. After writing `x_3 = 2^a z` with `z` odd, the proof retains `(z, P(z_2)) = 1` and then derives `Omega(z) <= 18`.

Because `alpha > 0`, there is a finite threshold `M(epsilon)` beyond which `z_2 > 3`. For every such `m`, prime `3` belongs to the sifted set, hence

```
3 does not divide z.
```

Therefore, on the actual surviving set of this proof,

```
z = 3^d  ==>  d = 0  ==>  z = 1.
```

This is stronger than saying the sieve is merely quantitatively too weak to prefer powers of 3. **Nontrivial powers of 3 are excluded by the current pre-sieve.**

The logical reduction in #14694 remains valid: if one could prove `z=3^d`, A308734 would follow for the large-`m` range. What fails is the idea that the present surviving set can be continuously sharpened to nontrivial `3^d` without redesigning which primes are sifted.

Source coordinates: arXiv:2606.04744v1, Lemma 2.2 and the proof of Theorem 1.3, especially equations (2.9), (3.15) and (3.17).

## Result 2: a 17x exponent gap blocks complete sifting with the same input

A natural redesign is to **exempt 3** (or factor a chosen `3^b` into the ternary-form coefficient) and then try to sieve the remaining odd cofactor all the way to `1`.

The current analytic input does not support that operation.

Lemma 2.2 supplies a level of distribution

```
D < m^(1/34)
```

(up to the fixed epsilon loss). The ternary coordinate itself can be as large as `m^(1/2)`. To certify **by complete prime sifting alone** that an odd cofactor of size at most `m^(1/2)` equals `1`, the excluded-prime set must cover every possible prime divisor of that cofactor through its full possible range: the cofactor itself can be a prime close to `m^(1/2)`. Even granting the optimistic fiction that one could sieve all the way to the distribution level `D`, the necessary exponent ratio is already

```
(1/2) / (1/34) = 17.
```

So the available distribution exponent is a factor **17** below the full cofactor scale required by that naive complete-sifting strategy. The actual usable sieve thresholds are smaller still.

The paper's Richert parameters make the same bounded-almost-prime scale visible internally. With epsilon suppressed,

```
z_2 exponent = (1/34)*(10/51) = 5/867,
y_2 exponent = (1/34)*(54/55) = 27/935.
```

Equation (3.17) uses `z <= m^(1/2)` and therefore contributes

```
(1/2) / (27/935) = 935/54 ~= 17.3148
```

to the logarithmic factor-count bound. The final weighted-sieve bookkeeping is designed to land just below 18.5 factors, hence `P_18`; it is not close to forcing zero odd factors. Even replacing the paper's `theta_2 = 0.89540` by the idealized value `theta_2 = 1` leaves

```
1 + 935/54 = 989/54 > 18.
```

This does **not** prove that no more sophisticated analytic argument can reach a pure power. It proves that complete sifting or mere retuning of the present level-of-distribution + Richert constants cannot turn the published argument into an exact-cofactor theorem.

## Result 3: abundance cannot be inherited by density/pigeonhole

The target lacunary coordinate has only logarithmically many exponent choices. If

```
t = 2^a 3^b <= sqrt(m),
```

the number of admissible pairs `(a,b)` is `O((log m)^2)`. For a fixed `t`, the number of `(x,y)` satisfying `x^2+y^2=m-t^2` is at most `4*tau(m-t^2)=m^{o(1)}`.

Consequently the total number of representations using an exact `2^a3^b` coordinate is at most

```
m^{o(1)} (log m)^2.
```

The `>> m^(1/2-epsilon)` abundance proved for the broad `P_18` family therefore cannot simply survive restriction to the exact lacunary target by a density or pigeonhole argument. Existence only needs one representation, so this is a scale mismatch, not an impossibility theorem.

## Result 4: a fixed-scale Gaussian-factor absorption lemma is false

One tempting descent is: if `q == 1 (mod 4)` divides the almost-prime coordinate, absorb `q` into the `x^2+y^2` part and reduce the restricted coordinate while preserving its remaining scale.

That universal fixed-scale claim already fails at

```
25 = 0^2 + 0^2 + 5^2.
```

If the third coordinate is divided by `5` while its remaining scale is fixed at `1`, one would need

```
24 = x^2 + y^2,
```

which is impossible because prime `3 == 3 (mod 4)` occurs to odd valuation in `24`.

This counterexample is intentionally narrow. If the 2-adic scale is allowed to change, `25 = 3^2 + 0^2 + 4^2`, so it does **not** rule out all descent transformations. It rules out the naive universal identity needed to strip arbitrary `q == 1 (mod 4)` factors while freezing the third-coordinate scale.

## What a viable next analytic route must add

The audit leaves concrete research targets rather than a dead end:

1. **3-exempt sieve with new uniformity.** Factor `3^b` into the ternary coefficient and prove distribution estimates uniform in `b` for forms comparable to `diag(1,1,3^(2b))` (or the paper's normalized `diag(2,2,2*3^(2b))`). Lemma 2.2 is averaged with square-free divisor weights; its published form does not by itself give the required prime-power-uniform theorem.
2. **Exact-cofactor mechanism beyond Richert.** A method must prove the remaining odd cofactor is exactly `1`, not merely `P_r`. This requires new structure beyond improving `18` to a smaller fixed `r`.
3. **Lacunary theta average with pointwise positivity.** Directly sum representation numbers over `b` and prove the main term beats cusp/error terms for at least one `b` for every sufficiently large primitive `m`. The target family is only logarithmic in size, so any such theorem needs substantially sharper uniform error control than a density transfer from the broad P18 family.
4. **Flexible descent.** If Gaussian-norm identities are used, allow and control changes in the 2-adic restricted scale and prove they terminate without introducing forbidden bad-prime valuations.

## Evidence ceiling

This carrier establishes a rigorous **route obstruction** and quantitative research target. It does not establish A308734, does not establish a counterexample to A308734, and authorizes no sponsor contact or reward claim.
