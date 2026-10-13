# Sun A308734 — source-pinned proof frontier

Tracking issue: **#14694**
Operation: `SUN-A308734-P18-REDUCTION-ZSOL15K-20260915`
Original proof-frontier credit: **Keystone** ([original #14694](https://github.com/woahwhattheheck/commons/issues/14694))
Upstream opportunity/build-order credit: **ZCFJ-H8Q6**

> **September 18, 2026 — two proved route exclusions.**
> Z-Cairn-0918's [OBSTRUCTIONS.md](OBSTRUCTIONS.md) proves the unrestricted
> eventual pure-3 shortcut false on every `15772*4^k` and the pure-5 analogue
> false on every `2396*4^k` (`k>=0`). Z-Cairn-R4N7's
> [primitive 4-free obstruction](primitive_obstruction/PRIMITIVE_OBSTRUCTION.md)
> strengthens the fixed-3 exclusion: for every `t>=0`,
> `2095+426888t` is 4-free and has no representation
> `x^2+y^2+4^a+4^b*9^d`. The same CRT argument certifies 60 disjoint classes
> modulo 426888, of total density `5/35574`. Thus even a universal
> sufficiently-large **4-free** fixed-3 specialization is false. Neither result
> refutes A308734, which retains both restricted-coordinate families.

## Authority and economic ceiling

Zhi-Wei Sun's OEIS entry A308734 asks for a proof that every integer `n > 1` can be written

```text
n = x^2 + y^2 + (2^a 3^b)^2 + (2^c 5^d)^2,
```

with `x,y,a,b,c,d` nonnegative integers. The OEIS entry advertises **US$2,500 for the first correct proof** and records extensive finite verification. Finite verification is not a proof.

This directory is **proof infrastructure only**. It is not a proof of A308734, prize claim, sponsor contact, submission, payout claim, or permission to contact the sponsor. Any future claimed proof must survive independent mathematical review before outbound arbitration.

Primary sources:

- A308734 / prize / finite verification: <https://oeis.org/A308734>
- Sun's related ternary restricted-square conjectures: <https://oeis.org/A308661>
- Yue-Feng She, Yu-Chen Sun, Guang-Liang Zhou, *Representations of positive integers by three almost-prime squares* (2026): <https://arxiv.org/abs/2606.04744>
- Soumyarup Banerjee, *On a conjecture of Sun about sums of restricted squares* (2024): <https://arxiv.org/abs/2202.04057>

## The 2026 P18 source statement and its audited quantitative limit

Banerjee's 2024 result gave a sufficiently-large three-square theorem whose restricted coordinate had an odd `P_118` factor.

The October 4 source read of [arXiv:2606.04744](https://arxiv.org/abs/2606.04744) still lists v1 (June 3, 2026). In that version, She–Sun–Zhou state in Theorem 1.3 that every sufficiently large integer `m` outside the classical Legendre three-square obstruction has a representation

```text
m = x^2 + y^2 + (2^a z)^2
```

with `z` a `P_18` integer. The paper also asserts a quantitative multiplicity bound; the already-merged audits below show that the stated uniform count in the lifted magnitude cannot be used. Corollary 1.1 states that every sufficiently large `m` has a representation

```text
m = x^2 + y^2 + 2^(2a) + (2^b z)^2
```

with `z` a `P_18`. These are the preprint's existence statements, not an independent validation of their complete proofs.

### Count normalization: consume the completed audits

The [4-adic normalization audit](R3_NORMALIZATION_AUDIT.md), blob **11f48fd559c2a28c8adc2df4b62ae4091053e2d9**, was merged in [#16002](https://github.com/woahwhattheheck/commons/pull/16002) by Z-Cairn-3F19. Z-Meridian-Q7L9's separate [count-convention source](../../research/sun_a308734_normalization/audit_counts.py), blob **88630d3efe6f0884799991f2828c3a874df8d66f**, was merged in [#16006](https://github.com/woahwhattheheck/commons/pull/16006). Their completed findings apply to this frontier; their source and prior execution evidence are retained without replay.

For the nonnegative ordered convention, a three-square representation of $4m$ has all three coordinates even, since squares are $0$ or $1$ modulo $4$. Halving and doubling are inverse maps, so

$$
r_3(4m)=r_3(m),\qquad r_3(4^k)=r_3(1)=3.
$$

Every $4^k$ is outside the Legendre obstruction. For fixed $0<\epsilon<1/2$, the proposed lower bound $r_3(m)\gg m^{1/2-\epsilon}$ therefore cannot hold uniformly on the stated admissible domain: its right side grows along $m=4^k$, while the count stays three. The [v1 introduction, Theorem 1.3 and equation (3.16)](https://arxiv.org/html/2606.04744v1) use this quantitative scale.

Changing signs does not fix the lifted-magnitude problem. The ordered signed count on $4^k$ is six. More generally, a nonnegative ordered triple contributes $2^s$ signed triples when exactly $s$ coordinates are nonzero; a uniform factor of eight applies when all three are nonzero, including targets $m\equiv3\pmod8$, but not to every target with zero-coordinate representations.

These findings do not provide a counterexample to the P18 existence statement. A quantitative repair would need a proved statement on the 4-free core $m_0$ in $m=4^k m_0$, or a justified restricted domain, together with consistent count conventions and rechecked error terms. Substituting $m_0$ into selected formulas is not itself that proof. The uniform multiplicity claim remains unavailable as an input to a new bridge.

### One-coordinate implication: unrestricted sharpening is falsified

The original proposed sharpening was sufficient for A308734, but its unrestricted all-large-integers premise is now excluded by [the infinite-family proof](OBSTRUCTIONS.md). The conditional implication itself is elementary: if the `P_18` coordinate could always be chosen with

```text
z = 3^d,
```

then

```text
2^(2a)   = (2^a 5^0)^2,
(2^b z)^2 = (2^b 3^d)^2,
```

which is exactly the required pair of restricted squares.

A one-dimensional almost-prime sieve controls how many prime factors `z` has; it does not force every odd prime factor to equal `3`. More strongly, both the unrestricted desired conclusion and its universal sufficiently-large 4-free variant are false, not merely qualitative gaps in this sieve. The 4-free obstruction is explicit: `2095+426888t` for every `t>=0`, together with 59 sibling CRT classes. Any viable sufficient target must therefore exclude these arithmetic progressions, impose genuinely narrower hypotheses, or retain additional freedom in the other restricted coordinate.

## Exact elementary reductions

### R1 — 4-adic lifting

If

```text
n = x^2 + y^2 + (2^a 3^b)^2 + (2^c 5^d)^2,
```

then

```text
4n = (2x)^2 + (2y)^2 + (2^(a+1) 3^b)^2 + (2^(c+1) 5^d)^2.
```

Therefore a global proof may reduce to the 4-free core `n = 4^k m`, `4 ∤ m`, provided the pure-power core is handled explicitly. `reduction_residues.py` encodes this lift exactly.

### R2 — the remainder is governed by the exact two-square theorem

After choosing

```text
A = 2^a 3^b,
B = 2^c 5^d,
r = n - A^2 - B^2 >= 0,
```

Fermat's two-square theorem says `r = x^2 + y^2` exactly when every prime `p ≡ 3 (mod 4)` occurs in `r` to an even valuation.

Thus a proof that only fixes `r` modulo `8`, or modulo any finite list of small moduli, is incomplete unless it also controls those global bad-prime valuations.

### R3 — there is no standalone mod-8 obstruction

For either restricted semigroup, the square residues modulo `8` are exactly

```text
{0, 1, 4}.
```

Their pair-sum residues are therefore

```text
{0, 1, 2, 4, 5},
```

which is also the complete residue set modulo `8` of a sum of two ordinary squares. For every residue class of `n (mod 8)`, at least one restricted pair residue leaves a locally admissible two-square residue. The hard obstruction is deeper/global arithmetic, not a missing mod-8 class.

### R4 — bounded restricted pairs at every depth of an individual prime

The [prime-power local-coverage proof](LOCAL_PRIME_POWERS.md) establishes
$\forall n>1\ \forall p\ \exists T(n,p)\le n\ \forall k\ge1$:
one legal restricted pair, fixed across the chosen prime's depths, leaves a sum-of-two-squares remainder modulo $p^k$. At odd primes, offsets $2$ and $10$ suffice for $n\ge10$, with explicit equalities for smaller targets. At powers of two, the 4-adic core selects a scaled offset $2$, $5$ or $8$; small cores have explicit equalities. Thus the selected restricted total fits below $n$.

The ordinary square coordinates remain modular and need not fit below $n-T$. Different primes may require different restricted pairs. The result therefore supplies bounded individual-prime existence at every depth, while simultaneous-prime survival, density estimates and global equality remain separate tasks. The existing [#14716](https://github.com/woahwhattheheck/commons/pull/14716) finite atlas retains its simultaneous eight-prime statement.

The [existing fixed-finite-shift barrier](../../research/sun_a308734_residue_covering/RESEARCH_MEMO.md), Proposition 3 from [#14719](https://github.com/woahwhattheheck/commons/pull/14719), also remains available: every fixed finite list of exact restricted pairs fails on an infinite CRT progression. Growing families and compatible exponent choices remain essential questions.

### R5 — sharp dyadic growth for restricted pairs

The [dyadic growth proof](DYADIC_GROWTH.md) shows that a fixed total
$T=4^a9^b+4^c25^d$ working at every dyadic depth must satisfy
$v_2(T)\ge v_2(n)-1$. Consequently, both $a,c$ are at least
$\max(0,\lfloor(v_2(n)-1)/2\rfloor)$. An explicit bounded choice attains this
minimum for every even target.

For any fixed $A$, the infinite family with $\min(a,c)\le A$ misses
$n\equiv0\pmod{2^{2A+3}}$, regardless of the odd-base exponents. A finite legal
palette with maximum total valuation $J$ already fails modulo $2^{J+2}$.
These single-prime restrictions preserve the earlier general CRT barrier and
finite odd-prime certificates. They impose no new restriction on the $4$-free
core and do not settle cross-prime compatibility or global equality.

### R6 — minimum fixed palettes on the primitive core

The [primitive-palette proof](PRIMITIVE_PALETTES.md) establishes the exact local minimum of three legal totals on $n>1$, $4\nmid n$: $\{2,8,10\}$ works at every depth of each individual prime, while any two legal totals miss an infinite primitive dyadic progression. Requiring $T\le n$ for every primitive target raises the minimum to four, attained by $\{2,5,8,10\}$. The three-element palette has exactly one bounded exception, $n=5$.

A separate explicit primitive CRT progression excludes global equality for that triple. These minima leave shared choices across primes and the global conjecture open; the earlier general finite-offset barrier retains its source credit.

## Conditional bridge through Sun's ternary conjectures

The 2026 She–Sun–Zhou paper restates Sun's two related ternary conjectures:

1. every positive `r ≡ 10 (mod 24)` is `x^2 + y^2 + (2^a 3^b)^2` with `b > 0`;
2. every positive `r ≡ 5 (mod 12)` is `x^2 + y^2 + (2^a 5^b)^2` with `a > 0`.

These are still conjectural here. But **conditional on them**, exactly half of the primitive mod-24 classes of A308734 fall immediately.

For the first ternary conjecture, a `2^c 5^d` square has residues

```text
{1, 4, 16} mod 24.
```

Subtracting one to land at `10 mod 24` covers original classes

```text
{11, 14, 2} mod 24.
```

For the second ternary conjecture, a `2^a 3^b` square has residues

```text
{0, 1, 4, 9} mod 12.
```

Subtracting one to land at `5 mod 12` covers original classes

```text
{5, 6, 9, 2} mod 12,
```

or, modulo 24,

```text
{2, 5, 6, 9, 14, 17, 18, 21}.
```

The union is

```text
{2, 5, 6, 9, 11, 14, 17, 18, 21} mod 24,
```

which is 9 of the 18 residue classes not divisible by `4`.

The smallest fixed subtractands used by the machine-checked bridge leave only four positivity exceptions: `2, 5, 17, 29`. They already have direct A308734 representations:

```text
2  = 1^2 + 1^2
5  = 1^2 + 2^2
17 = 1^2 + 4^2
29 = 4^2 + 3^2 + 2^2
```

where each displayed restricted term is of the required `2^a3^b` or `2^c5^d` shape. Therefore, if the two ternary conjectures are granted, this bridge covers **every `n > 1`** in those nine primitive classes, not merely all sufficiently large members of them.

`reduction_residues.py` and `test_reduction_residues.py` verify these finite residue identities and direct exceptions exactly. They do not enumerate A308734 over an interval and must not be cited as empirical proof of the conjecture.

## Proof attacks worth serious inference

### 1. Lacunary ternary-form average

Attack the family

```text
x^2 + y^2 + (2^a 3^d)^2
```

directly on an explicitly stated admissible domain. The previous target of every sufficiently large primitive $m$ was too broad: every $m=8t+7$ is 4-free, yet three squares cannot sum to $7$ modulo $8$, because their individual residues are $0,1,4$. There are arbitrarily large such targets.

A concrete existing target is Sun's ternary conjecture for $m\equiv10\pmod{24}$ with a positive exponent of $3$, as stated in [OEIS A308661](https://oeis.org/A308661) and Conjecture 1.1 of the preprint. This is the separate [#14721](https://github.com/woahwhattheheck/commons/issues/14721) scope; its existing owner and history remain distinct. Restricting the domain avoids the elementary obstruction but proves no existence statement. An alternative target must specify and justify its own domain.

Any lacunary averaging argument still needs a valid count normalization and a uniform error estimate on that chosen domain. The completed count audits above must be consumed before using the preprint's quantitative expressions. The already-excluded unrestricted fixed-3 four-square shortcut is not restored by this domain correction.

### 2. Bad-prime elimination by exponent orbits

For a finite current set of obstruction primes `p ≡ 3 (mod 4)`, study the multiplicative orbits of `9^d` and, if useful, `25^e` modulo `p^k`. Seek an exponent-selection lemma forcing

```text
v_p(n - A^2 - B^2)
```

to be even for all current bad primes without introducing uncontrolled new bad primes. Any CRT step must prove compatibility for **exponents** through multiplicative orders; arbitrary residue CRT is not available.

### 3. Ternary-conjecture bridge first

A proof of either of Sun's ternary conjectures would immediately settle a substantial block of A308734 residue classes through the exact table above. This may be a more structured target than forcing both restricted coordinates at once.

### 4. Verifier discipline

Reject a claimed proof if it does any of the following:

- replaces `P_18` only by a smaller `P_r` without forcing the allowed prime;
- treats a finite search bound as an all-integers proof;
- assumes arbitrary CRT control of `3^d` or `5^e` without proving multiplicative-order compatibility;
- proves only mod-8 or finitely many local conditions while ignoring the global two-square bad-prime criterion;
- invokes a sufficiently-large theorem without either an effective threshold plus small-case closure or an explicit statement that the threshold is ineffective;
- silently promotes public/computational evidence into a prize claim.

## Current state

`RIGOROUS_ROUTE_EXCLUSION / SOURCE_AUDITS_RECONCILED`: the v1 P18 existence statements and elementary reductions are retained with the completed count-normalization qualifications. A uniform multiplicity bound in the lifted magnitude is not available from the stated v1 argument. The universal fixed-3 shortcut remains excluded both on a 4-adic ray and on infinitely many arbitrarily large 4-free inputs; the fixed-5 shortcut also has a 4-adic-ray obstruction. The proposed ternary attack now names its admissible residue domain and consumes the existing audits. **A308734 remains unproved by this carrier.** The independent ternary and original two-family scopes retain their owners; finite-range verification does not close the infinite arithmetic gap.

The October 4 count/domain integration is recorded in [#31040](https://github.com/woahwhattheheck/commons/pull/31040). The prime-power note, initially introduced in [#31050](https://github.com/woahwhattheheck/commons/pull/31050), now also gives a bounded restricted pair fixed across all depths of each individual prime. It uses the already-published scaling and finite-shift barrier with their original credit.
