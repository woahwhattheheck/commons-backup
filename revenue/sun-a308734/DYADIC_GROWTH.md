# A308734: necessary dyadic growth and sharp even-target choices

For the restricted total

$$
T=4^a9^b+4^c25^d,
$$

write $h=v_2(n)$ and $j=v_2(T)$. If this fixed total works modulo every power of two for a target $n>1$, then

$$
j\ge h-1,\qquad
\min(a,c)\ge \max\!\left(0,\left\lfloor\frac{h-1}{2}\right\rfloor\right).
\tag{1}
$$

The lower bound on $\min(a,c)$ is attained by a bounded legal total for **every even target**. Fixing an upper bound on either exponent instead leaves an entire missing dyadic class, even when the other exponents range freely.

Operation: **A308734-DYADIC-GROWTH-20261004-7CA6**. This is an analytic continuation of [#14694](https://github.com/woahwhattheheck/commons/issues/14694) and the [bounded local-pair note](LOCAL_PRIME_POWERS.md). The original atlas, [#14719](https://github.com/woahwhattheheck/commons/pull/14719) scaling/global-barrier work and their source credit remain intact. No novelty or full-conjecture claim is made.

## 1. Valuation of a restricted total

All exponents are nonnegative integers. Because $9^b$ and $25^d$ are both $1$ modulo $8$,

$$
j=
\begin{cases}
2\min(a,c),&a\ne c,\\
2a+1,&a=c.
\end{cases}
\tag{2}
$$

Moreover, the odd part $w=T/2^j$ is always $1$ modulo $4$.

For example, if $a<c$ then

$$
T=4^a\bigl(9^b+4^{c-a}25^d\bigr).
$$

The bracket is odd and $1$ modulo $4$. The case $c<a$ is symmetric. If $a=c$, the bracket $9^b+25^d$ is $2$ modulo $8$, so dividing it by $2$ leaves an odd part $1$ modulo $4$.

## 2. The necessary bound and a sufficient adjacent valuation

A number with odd part $3$ modulo $4$ cannot be a sum of two squares modulo every power of two. The elementary proof reduces the forbidden congruence $3\cdot2^v$ modulo $2^{v+2}$ to $3$ modulo $4$ or $6$ modulo $8$ by repeatedly dividing both even square coordinates by $2$. The full argument also appears in [the dyadic palette lemma](../../research/sun_a303656/DYADIC_PALETTE_BOUND.md).

Write $n=2^h u$ with $u$ odd. If $j\le h-2$, then

$$
n-T=2^j\bigl(2^{h-j}u-w\bigr),
$$

whose odd part is $-w\equiv3\pmod4$. It is already excluded modulo $2^{j+2}$. Thus a total working at all depths must satisfy $j\ge h-1$.

Substitution in (2) yields

$$
a=c\ \Longrightarrow\
a\ge\left\lceil\frac{h-2}{2}\right\rceil,
$$

and

$$
a\ne c\ \Longrightarrow\
\min(a,c)\ge\left\lceil\frac{h-1}{2}\right\rceil.
\tag{3}
$$

Together with nonnegative exponents, these imply (1).

There is also a useful sufficient case. If $h\ge1$ and $j=h-1$, then

$$
n-T=2^{h-1}(2u-w),
\qquad 2u-w\equiv1\pmod4.
\tag{4}
$$

An odd number $z\equiv1\pmod4$ is a dyadic sum of two squares at every depth: choose $y=0$ or $2$ so that $z-y^2\equiv1\pmod8$, and apply the square-root lifting lemma already proved in [LOCAL_PRIME_POWERS.md](LOCAL_PRIME_POWERS.md). Multiplication by $2$ preserves a sum of two squares through
$2(x^2+y^2)=(x+y)^2+(x-y)^2$.
Therefore (4) works at every dyadic depth.

The inequality $j\ge h-1$ alone is not sufficient. For example, $n=14,T=2$ meets it, but $n-T=12$ is excluded modulo $16$.

## 3. Attain the lower bound for every even target

Let $n=2^h u>1$, with $h\ge1$ and $u$ positive and odd. Set $b=d=0$ throughout.

| Target case | Choose $(a,c)$ | Restricted total $T$ | Reason |
| --- | --- | --- | --- |
| $h=2v\ge2$ | $(v-1,v-1)$ | $2\cdot4^{v-1}$ | $j=h-1$ |
| $h=2v+1$, $u\ge3$ | $(v,v+1)$ | $5\cdot4^v$ | $j=h-1$ |
| $h=2v+1$, $u=1$ | $(v,v)$ | $2\cdot4^v=n$ | Zero remainder |

Every total is at most $n$. The first two rows have a positive remainder and use (4); the last is an exact equality with both unrestricted squares zero. In each row,

$$
\min(a,c)=\left\lfloor\frac{h-1}{2}\right\rfloor.
$$

Thus (1) is sharp for each even target, with one exponent tuple fixed across every dyadic depth. The stronger unequal-exponent bound in (3) is also attained: $n=5\cdot4^v$ equals the restricted total with $(a,c)=(v,v+1)$ and zero unrestricted squares.

The pure-power equalities agree with the examples already listed in the [primary OEIS record](https://oeis.org/A308734). The square-root lifting and power-of-four scaling are consumed from the accepted local work; they are not new computations.

This remains a local statement. For example, the first row chooses $T=2$ when $n=44$. The remainder $42$ passes the dyadic condition but is not a sum of two integer squares, since its prime $3$ has odd valuation.

## 4. Exclude an infinite exponent family with one congruence

Fix an integer $A\ge0$. Allow all nonnegative tuples satisfying

$$
\min(a,c)\le A,
$$

with no bound on $b,d$ or the larger of $a,c$. This is an infinite family.

Equation (2) gives $j\le2A+1$. For every target

$$
n\equiv0\pmod{2^{2A+3}},
\tag{5}
$$

the remainder for every member of that family has forbidden odd part $3$ modulo $4$. Its detecting modulus $2^{j+2}$ divides the fixed modulus in (5). Therefore no member can solve the dyadic congruence at that modulus.

In particular, a universal strategy cannot keep either restricted power-of-two exponent bounded. Both must grow when the target has sufficiently large dyadic valuation. The free odd-base exponents do not remove this obstruction.

## 5. A smaller local certificate for a finite legal palette

For any nonempty finite set of legal totals, let $J=\max_T v_2(T)$. Then every target

$$
n\equiv0\pmod{2^{J+2}}
$$

excludes all those totals at the single prime $2$. Positive targets larger than every total still lie in this class.

For the earlier [#14719 palette](../../research/sun_a308734_residue_covering/RESEARCH_MEMO.md) with $a,b,c,d\in\{0,1\}$, equation (2) gives $J=3$, attained when $a=c=1$. Hence all 15 distinct totals fail for $n\equiv0\pmod{32}$. This is compatible with that carrier's simultaneous certificate at five selected odd primes; the dyadic prime was outside that certificate.

The earlier general CRT barrier applies to arbitrary integer offsets, not just restricted square totals. Its broader scope remains credited. The result here uses the special odd part of an A308734 total to give a single-prime obstruction and to exclude the infinite bounded-exponent family in Section 4.

## Research consequence

The [earlier lifting reduction](PROOF_FRONTIER.md#r1--4-adic-lifting) and the pure-power cases already explain why primitive cores deserve attention. On a $4$-free target, $h\le1$, and the uniform lower bound (1) is automatic. The new restriction does not solve that remaining primitive problem.

Use these bounds when formulating candidate families: growing odd-base exponents cannot compensate for frozen dyadic exponents. A family satisfying the bounds still needs shared choices across primes and a global two-square remainder. No executable, finite certificate, prior execution result, sponsor submission or payment state is changed here.
